"""Note operations and note-analysis orchestration."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from app.logging import get_logger
from app.models import (
    Note,
    NoteCreate,
    NoteUpdate,
    NoteStatus,
    NoteAnalysisResult,
    EntityExtraction,
    RelationExtraction,
    normalize_type,
)
from app.services.backboard import BackboardService
from app.services.lore_entities import LoreEntityService
from app.services.lore_relations import LoreRelationService
from app.services.prompts import build_analysis_prompt

logger = get_logger("services.lore_notes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    ):
        self.db_path = db_path
        self.backboard = backboard
        self.entity_service = entity_service
        self.relation_service = relation_service

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
        lines = []
        for e in entities:
            aliases_str = f" (aka {', '.join(e.aliases)})" if e.aliases else ""
            lines.append(f"- {e.name}{aliases_str} [{e.type}]")
        return "Known entities:\n" + "\n".join(lines)

    def _parse_extraction(self, raw_response: str) -> NoteAnalysisResult:
        text = raw_response.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}")
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
        return NoteAnalysisResult(success=True, entities=entities, relations=relations)

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
        prompt = build_analysis_prompt(note.content, entity_context)

        thread_id = note.analysis_thread_id
        if not thread_id:
            thread_result = await self.backboard.create_thread(assistant_id)
            if not thread_result.success or not thread_result.id:
                raise ValueError("Failed to create analysis thread")
            thread_id = thread_result.id

        chat_result = await self.backboard.chat(thread_id=thread_id, prompt=prompt)
        if not chat_result.success or not chat_result.response:
            raise ValueError("AI analysis returned no response")

        extraction = self._parse_extraction(chat_result.response)
        summary = await self._merge_extraction(world_id, note_id, extraction)

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
            f"{summary['relations_created']} relations created"
        )
        return summary

    async def _merge_extraction(
        self, world_id: str, note_id: str, extraction: NoteAnalysisResult
    ) -> dict:
        entities_created = 0
        entities_updated = 0
        relations_created = 0

        existing = await self.entity_service.list_entities(world_id)
        name_map: dict[str, object] = {}
        for e in existing:
            name_map[e.name.lower()] = e
            for alias in e.aliases:
                name_map[alias.lower()] = e

        name_to_id: dict[str, str] = {e.name.lower(): e.id for e in existing}
        for e in existing:
            for alias in e.aliases:
                name_to_id[alias.lower()] = e.id

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
                    note_id=note_id,
                    extracted=ext_entity,
                )
                name_to_id[ext_entity.name.lower()] = new_id
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
            exists = await self.relation_service.relation_exists(
                world_id=world_id,
                source_id=source_id,
                target_id=target_id,
                relation_type=ext_rel.type,
            )
            if exists:
                continue
            await self.relation_service.create_ai_relation(
                world_id=world_id,
                note_id=note_id,
                source_id=source_id,
                target_id=target_id,
                relation_type=ext_rel.type,
                context=ext_rel.context,
            )
            relations_created += 1

        return {
            "entities_created": entities_created,
            "entities_updated": entities_updated,
            "relations_created": relations_created,
        }
