"""Note operations and note-analysis orchestration."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from app.config import settings
from app.logging import get_logger
from app.models import (
    EntityExtraction,
    EntitySource,
    Note,
    NoteAnalysisResult,
    NoteCreate,
    NoteStatus,
    NoteUpdate,
    RelationExtraction,
    TimelineMarkerChangeExtraction,
    TimelineMarkerCreate,
    TimelineMarkerExtraction,
    TimelineOperationCreate,
    normalize_type,
)
from app.services.backboard import BackboardService
from app.services.lore_entities import LoreEntityService
from app.services.lore_relations import LoreRelationService
from app.services.prompts import build_analysis_prompt
from app.services.timeline import TimelineService

logger = get_logger("services.lore_notes")

VALID_MARKER_KINDS = {"explicit", "semantic"}
VALID_TARGET_KINDS = {"entity", "relation", "world"}
GENERIC_PATCH_ALIASES = {"patch", "update", "modify", "edit", "operation_patch"}
GENERIC_CREATE_ALIASES = {"create", "add", "insert", "spawn", "introduce"}
GENERIC_DELETE_ALIASES = {"delete", "remove", "erase", "destroy", "eliminate", "kill", "die"}
ENTITY_DELETE_HINTS = {
    "died",
    "dead",
    "deceased",
    "perished",
    "killed",
    "slain",
    "executed",
    "assassinated",
    "murdered",
    "destroyed",
    "was killed",
    "has died",
}
SUPPORTED_ENTITY_OPS = {"entity_create", "entity_patch", "entity_delete"}
SUPPORTED_RELATION_OPS = {"relation_create", "relation_patch", "relation_delete"}
SUPPORTED_WORLD_OPS = {"world_patch"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_marker_kind(kind: str | None) -> str:
    normalized = normalize_type(kind or "semantic")
    return normalized if normalized in VALID_MARKER_KINDS else "semantic"


def _normalize_target_kind(kind: str | None) -> str:
    normalized = normalize_type(kind or "entity")
    return normalized if normalized in VALID_TARGET_KINDS else "entity"


def _default_patch_op(target_kind: str) -> str:
    if target_kind == "world":
        return "world_patch"
    return f"{target_kind}_patch"


def _default_create_op(target_kind: str) -> str:
    if target_kind == "world":
        return "world_patch"
    return f"{target_kind}_create"


def _default_delete_op(target_kind: str) -> str:
    if target_kind == "world":
        return "world_patch"
    return f"{target_kind}_delete"


def _is_supported_for_target(target_kind: str, op_type: str) -> bool:
    if target_kind == "entity":
        return op_type in SUPPORTED_ENTITY_OPS
    if target_kind == "relation":
        return op_type in SUPPORTED_RELATION_OPS
    return op_type in SUPPORTED_WORLD_OPS


def _contains_entity_delete_hint(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ENTITY_DELETE_HINTS)


def _is_timeout_error_message(error: str | None) -> bool:
    message = str(error or "").lower()
    return "timed out" in message or "timeout" in message


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 15)] + "...<truncated>"


def _coerce_date_sort_value(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _canonical_ai_op_type(
    raw_op_type: str | None,
    target_kind: str,
    payload: dict[str, Any],
    marker_title: str | None = None,
    marker_summary: str | None = None,
) -> str:
    normalized = normalize_type(raw_op_type or "")

    if not normalized:
        normalized = _default_patch_op(target_kind)

    if normalized in GENERIC_PATCH_ALIASES:
        normalized = _default_patch_op(target_kind)
    elif normalized in GENERIC_CREATE_ALIASES:
        normalized = _default_create_op(target_kind)
    elif normalized in GENERIC_DELETE_ALIASES:
        normalized = _default_delete_op(target_kind)
    elif normalized.endswith("_add"):
        normalized = normalized.replace("_add", "_create")
    elif normalized.endswith("_update") or normalized.endswith("_modify"):
        normalized = normalized.rsplit("_", 1)[0] + "_patch"
    elif normalized.endswith("_remove"):
        normalized = normalized.rsplit("_", 1)[0] + "_delete"

    if target_kind == "entity" and normalized == "entity_patch":
        signal_text = " ".join(
            [
                marker_title or "",
                marker_summary or "",
                str(payload.get("status") or ""),
                str(payload.get("state") or ""),
                str(payload.get("summary") or ""),
                str(payload.get("context") or ""),
            ]
        )
        if _contains_entity_delete_hint(signal_text):
            normalized = "entity_delete"

    if not _is_supported_for_target(target_kind, normalized):
        normalized = _default_patch_op(target_kind)

    return normalized


def _row_to_note(row: dict) -> Note:
    return Note(
        id=row["id"],
        world_id=row["world_id"],
        title=row.get("title"),
        content=row["content"],
        status=row["status"],
        analysis_thread_id=row.get("analysis_thread_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class LoreNoteService:
    def __init__(
        self,
        db_path: str,
        backboard: BackboardService,
        entity_service: LoreEntityService,
        relation_service: LoreRelationService,
        timeline_service: TimelineService,
    ):
        self.db_path = db_path
        self.backboard = backboard
        self.entity_service = entity_service
        self.relation_service = relation_service
        self.timeline_service = timeline_service

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def create_note(self, world_id: str, data: NoteCreate) -> Note:
        now = _now()
        note = Note(
            id=str(uuid4()),
            world_id=world_id,
            title=data.title,
            content=data.content,
            status=NoteStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO notes (id, world_id, title, content, status, analysis_thread_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    note.id,
                    note.world_id,
                    note.title,
                    note.content,
                    note.status.value,
                    note.analysis_thread_id,
                    note.created_at,
                    note.updated_at,
                ),
            )
            await db.commit()
        finally:
            await db.close()
        return note

    async def get_note(self, world_id: str, note_id: str) -> Note | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM notes WHERE id = ? AND world_id = ?",
                (note_id, world_id),
            )
            row = await cursor.fetchone()
            return _row_to_note(dict(row)) if row else None
        finally:
            await db.close()

    async def list_notes(self, world_id: str) -> list[Note]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM notes WHERE world_id = ? ORDER BY updated_at DESC",
                (world_id,),
            )
            rows = await cursor.fetchall()
            return [_row_to_note(dict(r)) for r in rows]
        finally:
            await db.close()

    async def update_note(
        self, world_id: str, note_id: str, data: NoteUpdate
    ) -> Note | None:
        existing = await self.get_note(world_id, note_id)
        if not existing:
            return None
        fields: dict = {}
        if data.title is not None:
            fields["title"] = data.title
        if data.content is not None:
            fields["content"] = data.content
            fields["status"] = NoteStatus.SAVED.value
        if not fields:
            return existing
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [note_id, world_id]
        db = await self._get_db()
        try:
            await db.execute(
                f"UPDATE notes SET {set_clause} WHERE id = ? AND world_id = ?",
                params,
            )
            await db.commit()
        finally:
            await db.close()
        return await self.get_note(world_id, note_id)

    async def delete_note(self, world_id: str, note_id: str) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "DELETE FROM notes WHERE id = ? AND world_id = ?",
                (note_id, world_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    def _build_entity_context(self, entities: list) -> str:
        if not entities:
            return "No entities exist in this world yet."
        max_entries = max(int(settings.NOTE_ANALYSIS_ENTITY_CONTEXT_MAX_ENTRIES), 1)
        max_chars = max(int(settings.NOTE_ANALYSIS_ENTITY_CONTEXT_MAX_CHARS), 800)
        total_entities = len(entities)
        selected_entities = entities[:max_entries]
        lines = []
        for e in selected_entities:
            aliases_str = f" (aka {', '.join(e.aliases)})" if e.aliases else ""
            lines.append(f"- {e.name}{aliases_str} [{e.type}]")
        context = "Known entities:\n" + "\n".join(lines)
        if total_entities > len(selected_entities):
            context += (
                f"\n... {total_entities - len(selected_entities)} additional entities omitted for prompt size."
            )
        return _truncate_text(context, max_chars)

    def _split_note_content(self, content: str) -> list[str]:
        text = (content or "").strip()
        if not text:
            return [""]

        max_chars = max(int(settings.NOTE_ANALYSIS_CHUNK_MAX_CHARS), 1500)
        overlap_chars = max(int(settings.NOTE_ANALYSIS_CHUNK_OVERLAP_CHARS), 0)
        overlap_chars = min(overlap_chars, max_chars // 3)
        max_chunks = max(int(settings.NOTE_ANALYSIS_MAX_CHUNKS), 1)

        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        start = 0
        text_len = len(text)
        while start < text_len and len(chunks) < max_chunks:
            hard_end = min(start + max_chars, text_len)
            if hard_end >= text_len:
                end = text_len
            else:
                search_start = max(start + int(max_chars * 0.6), start + 1)
                search_end = min(text_len, start + int(max_chars * 1.2))
                candidate = -1
                for delimiter in ("\n\n", "\n", ". "):
                    idx = text.rfind(delimiter, search_start, search_end)
                    if idx > candidate:
                        candidate = idx + len(delimiter)
                end = candidate if candidate > start else hard_end

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= text_len:
                break

            next_start = end - overlap_chars if overlap_chars > 0 else end
            if next_start <= start:
                next_start = end
            while next_start < text_len and text[next_start].isspace():
                next_start += 1
            start = next_start

        if start < text_len:
            tail = text[start:].strip()
            if tail:
                if chunks:
                    chunks[-1] = f"{chunks[-1]}\n\n{tail}"
                else:
                    chunks.append(tail)

        return chunks

    def _split_chunk_for_retry(self, content: str) -> list[str]:
        text = (content or "").strip()
        min_chars = max(int(settings.NOTE_ANALYSIS_TIMEOUT_SPLIT_MIN_CHARS), 600)
        if len(text) < min_chars * 2:
            return []

        midpoint = len(text) // 2
        search_start = max(min_chars, int(midpoint * 0.7))
        search_end = min(len(text) - min_chars, int(midpoint * 1.3))
        if search_start >= search_end:
            return []

        split_at = -1
        for delimiter in ("\n\n", "\n", ". "):
            idx = text.rfind(delimiter, search_start, search_end)
            if idx > split_at:
                split_at = idx + len(delimiter)
        if split_at <= 0:
            split_at = midpoint
        if split_at <= min_chars or split_at >= len(text) - min_chars:
            return []

        left = text[:split_at].strip()
        right = text[split_at:].strip()
        if not left or not right:
            return []
        return [left, right]

    def _extract_json_payload(self, raw_response: str) -> dict[str, Any]:
        text = raw_response.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for idx, char in enumerate(text):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

        raise ValueError("LLM returned invalid JSON payload")

    def _parse_extraction(self, raw_response: str) -> NoteAnalysisResult:
        try:
            data = self._extract_json_payload(raw_response)
        except ValueError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}")

        entities = [
            EntityExtraction(
                name=ent["name"],
                type=normalize_type(ent.get("type", "unknown")),
                subtype=ent.get("subtype"),
                aliases=ent.get("aliases", []),
                summary=ent.get("summary"),
                context=ent.get("context"),
                tags=ent.get("tags", []),
            )
            for ent in data.get("entities", [])
        ]
        relations = [
            RelationExtraction(
                source_name=rel["source_name"],
                target_name=rel["target_name"],
                type=normalize_type(rel.get("type", "related_to")),
                context=rel.get("context"),
            )
            for rel in data.get("relations", [])
        ]

        timeline_markers: list[TimelineMarkerExtraction] = []
        for marker in data.get("timeline_markers", []):
            marker_kind = _normalize_marker_kind(marker.get("marker_kind"))
            marker_title = marker.get("title")
            marker_summary = marker.get("summary")
            changes: list[TimelineMarkerChangeExtraction] = []
            for change in marker.get("changes", []):
                target_kind = _normalize_target_kind(change.get("target_kind"))
                payload = change.get("payload", {}) if isinstance(change.get("payload"), dict) else {}
                op_type = _canonical_ai_op_type(
                    raw_op_type=change.get("op_type"),
                    target_kind=target_kind,
                    payload=payload,
                    marker_title=marker_title,
                    marker_summary=marker_summary,
                )
                relation_type = change.get("relation_type")
                changes.append(
                    TimelineMarkerChangeExtraction(
                        op_type=op_type,
                        target_kind=target_kind,
                        target_name=change.get("target_name"),
                        source_name=change.get("source_name"),
                        relation_type=normalize_type(relation_type) if relation_type else None,
                        payload=payload,
                    )
                )

            timeline_markers.append(
                TimelineMarkerExtraction(
                    title=marker.get("title") or "Timeline Marker",
                    summary=marker.get("summary"),
                    marker_kind=marker_kind,
                    date_label=marker.get("date_label"),
                    date_sort_value=marker.get("date_sort_value"),
                    changes=changes,
                )
            )

        return NoteAnalysisResult(
            success=True,
            entities=entities,
            relations=relations,
            timeline_markers=timeline_markers,
        )

    def _combine_extractions(self, extractions: list[NoteAnalysisResult]) -> NoteAnalysisResult:
        if not extractions:
            return NoteAnalysisResult(success=True, entities=[], relations=[], timeline_markers=[])

        entity_map: dict[str, EntityExtraction] = {}
        relation_map: dict[tuple[str, str, str], RelationExtraction] = {}
        marker_map: dict[tuple[str, str, str, float | None], TimelineMarkerExtraction] = {}

        for extraction in extractions:
            for entity in extraction.entities:
                key = entity.name.strip().lower()
                if not key:
                    continue
                existing = entity_map.get(key)
                if not existing:
                    entity_map[key] = entity.model_copy(deep=True)
                    continue

                if (not existing.type or existing.type == "unknown") and entity.type:
                    existing.type = entity.type
                if not existing.subtype and entity.subtype:
                    existing.subtype = entity.subtype
                if entity.summary and (not existing.summary or len(entity.summary) > len(existing.summary)):
                    existing.summary = entity.summary
                if entity.context:
                    if not existing.context:
                        existing.context = entity.context
                    elif entity.context.lower() not in existing.context.lower():
                        existing.context = f"{existing.context}\n{entity.context}"

                existing.aliases = sorted(set([*existing.aliases, *entity.aliases]))
                existing.tags = sorted(set([*existing.tags, *entity.tags]))

            for relation in extraction.relations:
                key = (
                    relation.source_name.strip().lower(),
                    relation.target_name.strip().lower(),
                    normalize_type(relation.type),
                )
                existing = relation_map.get(key)
                if not existing:
                    relation_map[key] = relation.model_copy(deep=True)
                    continue
                if relation.context and not existing.context:
                    existing.context = relation.context
                elif relation.context and existing.context and relation.context.lower() not in existing.context.lower():
                    existing.context = f"{existing.context}\n{relation.context}"

            for marker in extraction.timeline_markers:
                marker_key = (
                    marker.title.strip().lower(),
                    marker.marker_kind,
                    (marker.date_label or "").strip().lower(),
                    float(marker.date_sort_value) if marker.date_sort_value is not None else None,
                )
                existing_marker = marker_map.get(marker_key)
                if not existing_marker:
                    marker_map[marker_key] = marker.model_copy(deep=True)
                    continue

                if marker.summary and not existing_marker.summary:
                    existing_marker.summary = marker.summary
                if marker.summary and existing_marker.summary and marker.summary.lower() not in existing_marker.summary.lower():
                    existing_marker.summary = f"{existing_marker.summary} {marker.summary}".strip()

                seen_changes: set[tuple[str, str, str, str, str, str]] = set()
                for change in existing_marker.changes:
                    seen_changes.add(
                        (
                            change.op_type,
                            change.target_kind,
                            (change.target_name or "").strip().lower(),
                            (change.source_name or "").strip().lower(),
                            normalize_type(change.relation_type or ""),
                            json.dumps(change.payload or {}, sort_keys=True, ensure_ascii=True),
                        )
                    )
                for change in marker.changes:
                    sig = (
                        change.op_type,
                        change.target_kind,
                        (change.target_name or "").strip().lower(),
                        (change.source_name or "").strip().lower(),
                        normalize_type(change.relation_type or ""),
                        json.dumps(change.payload or {}, sort_keys=True, ensure_ascii=True),
                    )
                    if sig in seen_changes:
                        continue
                    existing_marker.changes.append(change.model_copy(deep=True))
                    seen_changes.add(sig)

        return NoteAnalysisResult(
            success=True,
            entities=list(entity_map.values()),
            relations=list(relation_map.values()),
            timeline_markers=list(marker_map.values()),
        )

    async def _analyze_chunk_with_retries(
        self,
        *,
        assistant_id: str,
        note_id: str,
        thread_id: str,
        note_title: str | None,
        entity_context: str,
        chunk_content: str,
        chunk_label: str,
        chunk_index: int | None,
        chunk_total: int | None,
        split_depth: int = 0,
    ) -> tuple[list[NoteAnalysisResult], str]:
        parse_attempts = max(int(settings.NOTE_ANALYSIS_PARSE_ATTEMPTS), 1)
        timeout_split_max_depth = max(int(settings.NOTE_ANALYSIS_TIMEOUT_SPLIT_MAX_DEPTH), 0)

        prompt = build_analysis_prompt(
            note_title=note_title,
            note_content=chunk_content,
            entity_context=entity_context,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )

        extraction: NoteAnalysisResult | None = None
        last_error: Exception | None = None
        timeout_failure = False

        for attempt in range(1, parse_attempts + 1):
            chat_result = await self.backboard.chat(thread_id=thread_id, prompt=prompt, memory="off")
            if not chat_result.success or not chat_result.response:
                timeout_failure = _is_timeout_error_message(chat_result.error)
                last_error = ValueError(chat_result.error or "AI analysis returned no response")
                if timeout_failure:
                    replacement_thread = await self.backboard.create_thread(assistant_id)
                    if replacement_thread.success and replacement_thread.id:
                        previous_thread_id = thread_id
                        thread_id = replacement_thread.id
                        logger.warning(
                            "Chunk analyze timeout for note %s (%s); switching thread %s -> %s",
                            note_id,
                            chunk_label,
                            previous_thread_id,
                            thread_id,
                        )
                    else:
                        logger.warning(
                            "Chunk analyze timeout for note %s (%s); failed to create replacement thread",
                            note_id,
                            chunk_label,
                        )
                if attempt < parse_attempts:
                    logger.warning(
                        "Chunk analyze retry needed for note %s (%s) attempt %d/%d: %s",
                        note_id,
                        chunk_label,
                        attempt,
                        parse_attempts,
                        last_error,
                    )
                    continue
                break

            try:
                extraction = self._parse_extraction(chat_result.response)
                last_error = None
                break
            except Exception as exc:
                timeout_failure = False
                last_error = exc
                if attempt < parse_attempts:
                    logger.warning(
                        "Chunk parse retry needed for note %s (%s) attempt %d/%d: %s",
                        note_id,
                        chunk_label,
                        attempt,
                        parse_attempts,
                        exc,
                    )
                    continue

        if extraction:
            return [extraction], thread_id

        if timeout_failure and split_depth < timeout_split_max_depth:
            subchunks = self._split_chunk_for_retry(chunk_content)
            if subchunks:
                logger.warning(
                    "Chunk timeout split for note %s (%s): splitting into %d subchunks at depth %d",
                    note_id,
                    chunk_label,
                    len(subchunks),
                    split_depth + 1,
                )
                merged: list[NoteAnalysisResult] = []
                for sub_index, subchunk in enumerate(subchunks, start=1):
                    sub_label = f"{chunk_label}.{sub_index}"
                    sub_results, thread_id = await self._analyze_chunk_with_retries(
                        assistant_id=assistant_id,
                        note_id=note_id,
                        thread_id=thread_id,
                        note_title=note_title,
                        entity_context=entity_context,
                        chunk_content=subchunk,
                        chunk_label=sub_label,
                        chunk_index=None,
                        chunk_total=None,
                        split_depth=split_depth + 1,
                    )
                    merged.extend(sub_results)
                return merged, thread_id

        raise ValueError(
            f"Chunk analysis failed for note {note_id} at chunk {chunk_label}: {last_error}"
        )

    async def analyze_note(self, world_id: str, note_id: str) -> dict:
        note = await self.get_note(world_id, note_id)
        if not note:
            raise ValueError(f"Note {note_id} not found")
        if not self.backboard.is_available:
            raise ValueError("Backboard service is not available")

        assistant_id = await self.entity_service.get_world_assistant_id(world_id)
        if not assistant_id:
            raise ValueError(f"World {world_id} has no Backboard assistant configured")

        existing_entities = await self.entity_service.list_entities(world_id)
        entity_context = self._build_entity_context(existing_entities)
        content_chunks = self._split_note_content(note.content)
        chunk_total = len(content_chunks)
        if chunk_total > 1:
            logger.info(
                "Analyzing large note %s in %d chunks (chars=%d, chunk_max=%d, overlap=%d)",
                note_id,
                chunk_total,
                len(note.content or ""),
                settings.NOTE_ANALYSIS_CHUNK_MAX_CHARS,
                settings.NOTE_ANALYSIS_CHUNK_OVERLAP_CHARS,
            )

        thread_id = note.analysis_thread_id
        if not thread_id:
            thread_result = await self.backboard.create_thread(assistant_id)
            if not thread_result.success or not thread_result.id:
                raise ValueError("Failed to create analysis thread")
            thread_id = thread_result.id

        chunk_extractions: list[NoteAnalysisResult] = []
        for index, chunk_content in enumerate(content_chunks, start=1):
            results, thread_id = await self._analyze_chunk_with_retries(
                assistant_id=assistant_id,
                note_id=note_id,
                thread_id=thread_id,
                note_title=note.title,
                entity_context=entity_context,
                chunk_content=chunk_content,
                chunk_label=f"{index}/{chunk_total}",
                chunk_index=index if chunk_total > 1 else None,
                chunk_total=chunk_total if chunk_total > 1 else None,
                split_depth=0,
            )
            chunk_extractions.extend(results)

        extraction = self._combine_extractions(chunk_extractions)
        summary = await self._merge_extraction(world_id, note, extraction)

        db = await self._get_db()
        try:
            await db.execute(
                "UPDATE notes SET status = ?, analysis_thread_id = ?, updated_at = ? WHERE id = ? AND world_id = ?",
                (NoteStatus.ANALYZED.value, thread_id, _now(), note_id, world_id),
            )
            await db.commit()
        finally:
            await db.close()

        logger.info(
            f"Analysis complete for note {note_id[:8]}: "
            f"{summary['entities_created']} entities created, "
            f"{summary['entities_updated']} updated, "
            f"{summary['relations_created']} relations created, "
            f"{summary['timeline_markers_created']} timeline markers created"
        )
        return summary

    async def analyze_all_unanalyzed_notes(self, world_id: str) -> dict[str, Any]:
        notes = await self.list_notes(world_id)
        pending_notes = [note for note in notes if note.status != NoteStatus.ANALYZED]

        aggregate = {
            "notes_total": len(notes),
            "notes_skipped": len(notes) - len(pending_notes),
            "notes_analyzed": 0,
            "notes_failed": 0,
            "entities_created": 0,
            "entities_updated": 0,
            "relations_created": 0,
            "timeline_markers_created": 0,
            "failed_note_ids": [],
            "last_analyzed_note_id": None,
        }

        for note in pending_notes:
            try:
                summary = await self.analyze_note(world_id=world_id, note_id=note.id)
            except Exception as exc:
                aggregate["notes_failed"] += 1
                aggregate["failed_note_ids"].append(note.id)
                logger.warning(
                    f"Bulk analyze failed for note {note.id} in world {world_id}: {exc}",
                )
                continue

            aggregate["notes_analyzed"] += 1
            aggregate["last_analyzed_note_id"] = note.id
            aggregate["entities_created"] += int(summary.get("entities_created", 0))
            aggregate["entities_updated"] += int(summary.get("entities_updated", 0))
            aggregate["relations_created"] += int(summary.get("relations_created", 0))
            aggregate["timeline_markers_created"] += int(
                summary.get("timeline_markers_created", 0),
            )

        return aggregate

    async def _build_default_timeline_markers(
        self,
        note: Note,
        extraction: NoteAnalysisResult,
    ) -> list[TimelineMarkerExtraction]:
        default_changes: list[TimelineMarkerChangeExtraction] = []

        for ent in extraction.entities:
            payload: dict[str, Any] = {}
            if ent.summary:
                payload["summary"] = ent.summary
            if ent.context:
                payload["context"] = ent.context
            if ent.tags:
                payload["tags"] = ent.tags
            default_changes.append(
                TimelineMarkerChangeExtraction(
                    op_type="entity_patch",
                    target_kind="entity",
                    target_name=ent.name,
                    payload=payload,
                )
            )

        for rel in extraction.relations:
            payload: dict[str, Any] = {"type": rel.type}
            if rel.context:
                payload["context"] = rel.context
            default_changes.append(
                TimelineMarkerChangeExtraction(
                    op_type="relation_patch",
                    target_kind="relation",
                    source_name=rel.source_name,
                    target_name=rel.target_name,
                    relation_type=rel.type,
                    payload=payload,
                )
            )

        marker_title = note.title.strip() if note.title else f"Note {note.id[:8]}"
        marker_summary = "Auto-generated from note analysis."
        return [
            TimelineMarkerExtraction(
                title=marker_title,
                summary=marker_summary,
                marker_kind="semantic",
                changes=default_changes,
            )
        ]

    async def _append_timeline_markers(
        self,
        world_id: str,
        note: Note,
        extraction: NoteAnalysisResult,
        name_to_id: dict[str, str],
        name_to_display: dict[str, str],
        relation_key_to_id: dict[tuple[str, str, str], str],
    ) -> int:
        markers = extraction.timeline_markers or await self._build_default_timeline_markers(note, extraction)

        existing_markers = await self.timeline_service.list_markers(
            world_id=world_id,
            include_operations=False,
        )
        next_sort_key = max((marker.sort_key for marker in existing_markers), default=0.0) + 1.0

        created_count = 0
        for marker in markers:
            operations: list[TimelineOperationCreate] = []

            for index, change in enumerate(marker.changes):
                target_kind = _normalize_target_kind(change.target_kind)
                payload = dict(change.payload or {})
                op_type = _canonical_ai_op_type(
                    raw_op_type=change.op_type,
                    target_kind=target_kind,
                    payload=payload,
                    marker_title=marker.title,
                    marker_summary=marker.summary,
                )

                if target_kind == "entity":
                    target_name = (change.target_name or "").strip()
                    target_id = name_to_id.get(target_name.lower()) if target_name else None
                    if not target_id:
                        continue
                    if op_type == "entity_delete" and "status" not in payload:
                        delete_signal = " ".join(
                            [
                                marker.title or "",
                                marker.summary or "",
                                str(payload.get("summary") or ""),
                                str(payload.get("context") or ""),
                            ]
                        )
                        payload["status"] = (
                            "deceased" if _contains_entity_delete_hint(delete_signal) else "inactive"
                        )
                    if target_name:
                        payload.setdefault(
                            "name",
                            name_to_display.get(target_name.lower(), target_name),
                        )
                    operations.append(
                        TimelineOperationCreate(
                            op_type=op_type,
                            target_kind="entity",
                            target_id=target_id,
                            payload=payload,
                            order_index=index,
                        )
                    )
                    continue

                if target_kind == "relation":
                    source_name = (change.source_name or "").strip()
                    target_name = (change.target_name or "").strip()
                    source_id = name_to_id.get(source_name.lower()) if source_name else None
                    target_id_entity = name_to_id.get(target_name.lower()) if target_name else None
                    if not source_id or not target_id_entity:
                        continue

                    relation_type = normalize_type(
                        change.relation_type
                        or str(payload.get("type") or "related_to")
                    )
                    payload.setdefault("source_entity_id", source_id)
                    payload.setdefault("target_entity_id", target_id_entity)
                    payload.setdefault("type", relation_type)

                    relation_id = relation_key_to_id.get(
                        (source_id, target_id_entity, relation_type)
                    )
                    operations.append(
                        TimelineOperationCreate(
                            op_type=op_type,
                            target_kind="relation",
                            target_id=relation_id,
                            payload=payload,
                            order_index=index,
                        )
                    )
                    continue

                operations.append(
                    TimelineOperationCreate(
                        op_type=op_type,
                        target_kind="world",
                        target_id=None,
                        payload=payload,
                        order_index=index,
                    )
                )

            marker_kind = _normalize_marker_kind(marker.marker_kind)
            title = marker.title.strip() if marker.title else "Timeline Marker"
            date_sort_value = _coerce_date_sort_value(marker.date_sort_value)
            if marker_kind == "explicit" and date_sort_value is None:
                date_sort_value = _coerce_date_sort_value(marker.date_label)
            marker_sort_key = (
                None if marker_kind == "explicit" and date_sort_value is not None else next_sort_key
            )
            await self.timeline_service.create_marker(
                world_id=world_id,
                data=TimelineMarkerCreate(
                    title=title,
                    summary=marker.summary,
                    marker_kind=marker_kind,
                    placement_status="placed",
                    date_label=marker.date_label,
                    date_sort_value=date_sort_value,
                    sort_key=marker_sort_key,
                    source=EntitySource.AI,
                    source_note_id=note.id,
                    operations=operations,
                ),
            )
            if marker_sort_key is not None:
                next_sort_key += 1.0
            created_count += 1

        return created_count

    async def _merge_extraction(
        self,
        world_id: str,
        note: Note,
        extraction: NoteAnalysisResult,
    ) -> dict:
        entities_created = 0
        entities_updated = 0
        relations_created = 0

        existing = await self.entity_service.list_entities(world_id)
        name_map: dict[str, object] = {}
        name_to_id: dict[str, str] = {}
        name_to_display: dict[str, str] = {}
        for e in existing:
            lowered = e.name.lower()
            name_map[lowered] = e
            name_to_id[lowered] = e.id
            name_to_display[lowered] = e.name
            for alias in e.aliases:
                alias_lower = alias.lower()
                name_map[alias_lower] = e
                name_to_id[alias_lower] = e.id

        relation_key_to_id: dict[tuple[str, str, str], str] = {}
        existing_relations = await self.relation_service.list_relations(world_id)
        for rel in existing_relations:
            relation_key_to_id[(rel.source_entity_id, rel.target_entity_id, rel.type)] = rel.id

        for ext_entity in extraction.entities:
            matched = name_map.get(ext_entity.name.lower())
            if matched:
                merged_aliases = list(set(matched.aliases + ext_entity.aliases))
                merged_tags = list(set(matched.tags + ext_entity.tags))
                merged_context = await self.entity_service.merge_entity_context_with_llm(
                    world_id=world_id,
                    entity_name=matched.name,
                    entity_type=matched.type,
                    existing_context=matched.context,
                    incoming_context=ext_entity.context,
                )
                merged_summary = (
                    ext_entity.summary
                    if (ext_entity.summary and not matched.summary)
                    else matched.summary
                )
                await self.entity_service.update_merged_entity_fields(
                    world_id=world_id,
                    entity_id=matched.id,
                    merged_aliases=merged_aliases,
                    merged_tags=merged_tags,
                    merged_context=merged_context,
                    merged_summary=merged_summary,
                )
                entities_updated += 1
            else:
                new_id = await self.entity_service.create_ai_entity(
                    world_id=world_id,
                    note_id=note.id,
                    extracted=ext_entity,
                )
                name_to_id[ext_entity.name.lower()] = new_id
                name_to_display[ext_entity.name.lower()] = ext_entity.name
                for alias in ext_entity.aliases:
                    name_to_id[alias.lower()] = new_id
                entities_created += 1

        for ext_rel in extraction.relations:
            source_id = name_to_id.get(ext_rel.source_name.lower())
            target_id = name_to_id.get(ext_rel.target_name.lower())
            if not source_id or not target_id:
                logger.warning(
                    f"Skipping relation '{ext_rel.type}': could not resolve "
                    f"'{ext_rel.source_name}' -> '{ext_rel.target_name}'"
                )
                continue

            relation_key = (source_id, target_id, ext_rel.type)
            if relation_key in relation_key_to_id:
                continue

            relation_id = await self.relation_service.create_ai_relation(
                world_id=world_id,
                note_id=note.id,
                source_id=source_id,
                target_id=target_id,
                relation_type=ext_rel.type,
                context=ext_rel.context,
            )
            relation_key_to_id[relation_key] = relation_id
            relations_created += 1

        timeline_markers_created = await self._append_timeline_markers(
            world_id=world_id,
            note=note,
            extraction=extraction,
            name_to_id=name_to_id,
            name_to_display=name_to_display,
            relation_key_to_id=relation_key_to_id,
        )

        return {
            "entities_created": entities_created,
            "entities_updated": entities_updated,
            "relations_created": relations_created,
            "timeline_markers_created": timeline_markers_created,
        }
