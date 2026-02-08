"""Compile canonical world data into fixed Backboard RAG document slots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from app.logging import get_logger
from app.models import RagCompileRequest, RagCompileResult, RagDocumentSyncStatusResult
from app.services.backboard import BackboardService

logger = get_logger("services.world_rag_compiler")

ORG_ENTITY_TYPES = {"organization", "faction", "government", "house", "guild", "order", "clan"}
ITEM_ENTITY_TYPES = {"item", "artifact", "magic", "spell", "technology", "resource", "concept"}
SPATIAL_RELATION_TYPES = {
    "located_in",
    "location_of",
    "part_of",
    "contains",
    "inside",
    "within",
    "borders",
    "adjacent_to",
    "near",
    "north_of",
    "south_of",
    "east_of",
    "west_of",
    "capital_of",
    "resides_in",
    "based_in",
    "originates_from",
}
SPATIAL_RELATION_TOKENS = (
    "locat",
    "near",
    "adjacent",
    "north",
    "south",
    "east",
    "west",
    "contain",
    "within",
    "inside",
    "border",
    "region",
    "reside",
    "origin",
    "route",
    "capital",
)

RAG_SLOT_ORDER: list[tuple[str, str]] = [
    ("characters", "Characters"),
    ("locations", "Locations"),
    ("organizations_factions", "Organizations and Factions"),
    ("items_artifacts_magic", "Items, Artifacts, and Magic"),
    ("events", "Events"),
    ("relations_character", "Character Relations"),
    ("relations_spatial", "Spatial Relations"),
    ("timeline_ancient", "Timeline - Ancient"),
    ("timeline_past", "Timeline - Past"),
    ("timeline_present", "Timeline - Present"),
    ("notes_lore_volume_1", "Notes Lore Volume 1"),
    ("notes_lore_volume_2", "Notes Lore Volume 2"),
    ("notes_lore_volume_3", "Notes Lore Volume 3"),
    ("notes_lore_volume_4", "Notes Lore Volume 4"),
    ("notes_lore_volume_5", "Notes Lore Volume 5"),
    ("rules_invariants", "Rules and Invariants"),
]

RECOMMENDED_SPARE_SLOT_KEYS: list[tuple[str, str]] = [
    ("aliases_disambiguation", "Aliases and Disambiguation"),
    ("open_questions_retcons", "Open Questions and Retcons"),
    ("recent_changes_changelog", "Recent Changes Changelog"),
    ("mechanics_deep_dive", "Mechanics Deep Dive"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(value) for value in parsed]


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate_text(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    return value[: max(0, limit - 15)] + "...<truncated>"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _SlotContent:
    key: str
    title: str
    content: str
    record_count: int


class WorldRagCompilerService:
    """Compile a world into fixed RAG slots and sync them to Backboard."""

    def __init__(self, db_path: str, backboard: BackboardService):
        self.db_path = db_path
        self.backboard = backboard

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _get_world(self, db: aiosqlite.Connection, world_id: str) -> dict[str, Any] | None:
        cursor = await db.execute("SELECT * FROM worlds WHERE id = ?", (world_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _list_entities(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT id, world_id, name, type, subtype, aliases, summary, context, tags, status, created_at, updated_at
               FROM entities
               WHERE world_id = ?
               ORDER BY LOWER(name) ASC, created_at ASC, id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        entities: list[dict[str, Any]] = []
        for row in rows:
            entity = dict(row)
            entity["aliases"] = _load_json_list(entity.get("aliases"))
            entity["tags"] = _load_json_list(entity.get("tags"))
            entity["type"] = _normalize_text(entity.get("type")).lower()
            entity["subtype"] = _normalize_text(entity.get("subtype")).lower() or None
            entities.append(entity)
        return entities

    async def _list_relations(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT
                   r.id,
                   r.world_id,
                   r.source_entity_id,
                   r.target_entity_id,
                   r.type,
                   r.context,
                   r.created_at,
                   r.updated_at,
                   se.name AS source_name,
                   se.type AS source_type,
                   te.name AS target_name,
                   te.type AS target_type
               FROM relations r
               JOIN entities se ON se.id = r.source_entity_id
               JOIN entities te ON te.id = r.target_entity_id
               WHERE r.world_id = ?
               ORDER BY r.created_at ASC, r.id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        relations: list[dict[str, Any]] = []
        for row in rows:
            relation = dict(row)
            relation["type"] = _normalize_text(relation.get("type")).lower()
            relation["source_type"] = _normalize_text(relation.get("source_type")).lower()
            relation["target_type"] = _normalize_text(relation.get("target_type")).lower()
            relations.append(relation)
        return relations

    async def _list_markers(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT id, world_id, title, summary, marker_kind, placement_status, date_label, date_sort_value, sort_key, created_at, updated_at
               FROM timeline_markers
               WHERE world_id = ?
               ORDER BY sort_key ASC, created_at ASC, id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _list_operations(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT id, world_id, marker_id, op_type, target_kind, target_id, payload, order_index, created_at, updated_at
               FROM timeline_operations
               WHERE world_id = ?
               ORDER BY marker_id ASC, order_index ASC, created_at ASC, id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        operations: list[dict[str, Any]] = []
        for row in rows:
            operation = dict(row)
            payload_raw = operation.get("payload")
            if payload_raw:
                try:
                    payload = json.loads(payload_raw)
                except json.JSONDecodeError:
                    payload = {}
            else:
                payload = {}
            operation["payload"] = payload if isinstance(payload, dict) else {}
            operation["op_type"] = _normalize_text(operation.get("op_type")).lower()
            operation["target_kind"] = _normalize_text(operation.get("target_kind")).lower()
            operations.append(operation)
        return operations

    async def _list_notes(self, db: aiosqlite.Connection, world_id: str) -> list[dict[str, Any]]:
        cursor = await db.execute(
            """SELECT id, title, content, status, created_at, updated_at
               FROM notes
               WHERE world_id = ?
               ORDER BY updated_at DESC, created_at DESC, id DESC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _slot_records(self, db: aiosqlite.Connection, world_id: str) -> dict[str, dict[str, Any]]:
        cursor = await db.execute(
            """SELECT slot_key, slot_title, document_id, content_hash, content_size, record_count, updated_at
               FROM world_rag_documents
               WHERE world_id = ?""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return {row["slot_key"]: dict(row) for row in rows}

    async def _upsert_slot_record(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        assistant_id: str,
        slot_key: str,
        slot_title: str,
        document_id: str,
        content_hash: str,
        content_size: int,
        record_count: int,
    ) -> None:
        now = _now()
        await db.execute(
            """INSERT INTO world_rag_documents (
                   id, world_id, slot_key, slot_title, assistant_id, document_id,
                   content_hash, content_size, record_count, last_compiled_at, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(world_id, slot_key) DO UPDATE SET
                   slot_title = excluded.slot_title,
                   assistant_id = excluded.assistant_id,
                   document_id = excluded.document_id,
                   content_hash = excluded.content_hash,
                   content_size = excluded.content_size,
                   record_count = excluded.record_count,
                   last_compiled_at = excluded.last_compiled_at,
                   updated_at = excluded.updated_at""",
            (
                str(uuid4()),
                world_id,
                slot_key,
                slot_title,
                assistant_id,
                document_id,
                content_hash,
                content_size,
                record_count,
                now,
                now,
                now,
            ),
        )
        await db.commit()

    def _slot_document_type(self, slot_key: str) -> str:
        return f"rag_{slot_key}"

    def _render_header(self, world_name: str, world_description: str, slot_title: str) -> list[str]:
        return [
            f"# {slot_title}",
            f"World: {world_name}",
            f"Generated at (UTC): {_now()}",
            f"World description: {_normalize_text(world_description) or 'N/A'}",
            "",
        ]

    def _entity_slot_key(self, entity: dict[str, Any]) -> str:
        entity_type = _normalize_text(entity.get("type")).lower()
        subtype = _normalize_text(entity.get("subtype")).lower()
        tags = {_normalize_text(tag).lower() for tag in entity.get("tags", []) if tag}
        if entity_type == "character":
            return "characters"
        if entity_type == "location":
            return "locations"
        if entity_type in ORG_ENTITY_TYPES:
            return "organizations_factions"
        if entity_type == "event":
            return "events"
        if entity_type in ITEM_ENTITY_TYPES or "magic" in subtype or "magic" in tags:
            return "items_artifacts_magic"
        return "events"

    def _is_spatial_relation(self, relation: dict[str, Any]) -> bool:
        relation_type = _normalize_text(relation.get("type")).lower()
        source_type = _normalize_text(relation.get("source_type")).lower()
        target_type = _normalize_text(relation.get("target_type")).lower()
        if relation_type in SPATIAL_RELATION_TYPES:
            return True
        if any(token in relation_type for token in SPATIAL_RELATION_TOKENS):
            return True
        return source_type == "location" or target_type == "location"

    def _split_timeline(self, markers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        ancient: list[dict[str, Any]] = []
        past: list[dict[str, Any]] = []
        present: list[dict[str, Any]] = []
        marker_count = len(markers)
        if marker_count == 0:
            return {
                "timeline_ancient": ancient,
                "timeline_past": past,
                "timeline_present": present,
            }
        if marker_count == 1:
            present.append(markers[0])
            return {
                "timeline_ancient": ancient,
                "timeline_past": past,
                "timeline_present": present,
            }
        if marker_count == 2:
            past.append(markers[0])
            present.append(markers[1])
            return {
                "timeline_ancient": ancient,
                "timeline_past": past,
                "timeline_present": present,
            }
        first_cut = marker_count // 3
        second_cut = (2 * marker_count) // 3
        ancient = markers[:first_cut]
        past = markers[first_cut:second_cut]
        present = markers[second_cut:]
        return {
            "timeline_ancient": ancient,
            "timeline_past": past,
            "timeline_present": present,
        }

    def _split_notes_into_volumes(self, notes: list[dict[str, Any]], volume_count: int = 5) -> list[list[dict[str, Any]]]:
        if volume_count <= 0:
            return []
        if not notes:
            return [[] for _ in range(volume_count)]
        total = len(notes)
        q, r = divmod(total, volume_count)
        volumes: list[list[dict[str, Any]]] = []
        start = 0
        for index in range(volume_count):
            size = q + (1 if index < r else 0)
            end = start + size
            volumes.append(notes[start:end])
            start = end
        return volumes

    def _build_entities_doc(
        self,
        *,
        world_name: str,
        world_description: str,
        slot_title: str,
        entities: list[dict[str, Any]],
    ) -> str:
        lines = self._render_header(world_name, world_description, slot_title)
        lines.append(f"Total records: {len(entities)}")
        lines.append("")
        if not entities:
            lines.append("No records yet.")
        for entity in entities:
            aliases = ", ".join(_normalize_text(alias) for alias in entity.get("aliases", []) if alias) or "none"
            tags = ", ".join(_normalize_text(tag) for tag in entity.get("tags", []) if tag) or "none"
            subtype = _normalize_text(entity.get("subtype")) or "-"
            summary = _truncate_text(_normalize_text(entity.get("summary")), 260) or "-"
            context = _truncate_text(_normalize_text(entity.get("context")), 420) or "-"
            lines.append(
                f"- {entity.get('name')} (`{entity.get('id')}`) | "
                f"type={entity.get('type')} | subtype={subtype} | status={entity.get('status') or 'active'}"
            )
            lines.append(f"  aliases: {aliases}")
            lines.append(f"  tags: {tags}")
            lines.append(f"  summary: {summary}")
            lines.append(f"  context: {context}")
        return "\n".join(lines).strip() + "\n"

    def _build_relations_doc(
        self,
        *,
        world_name: str,
        world_description: str,
        slot_title: str,
        relations: list[dict[str, Any]],
    ) -> str:
        lines = self._render_header(world_name, world_description, slot_title)
        lines.append(f"Total records: {len(relations)}")
        lines.append("")
        if not relations:
            lines.append("No records yet.")
        for relation in relations:
            rel_context = _truncate_text(_normalize_text(relation.get("context")), 360) or "-"
            lines.append(
                f"- {relation.get('source_name')} (`{relation.get('source_entity_id')}`) "
                f"--{relation.get('type')}--> "
                f"{relation.get('target_name')} (`{relation.get('target_entity_id')}`) "
                f"[relation_id={relation.get('id')}]"
            )
            lines.append(f"  context: {rel_context}")
        return "\n".join(lines).strip() + "\n"

    def _build_timeline_doc(
        self,
        *,
        world_name: str,
        world_description: str,
        slot_title: str,
        markers: list[dict[str, Any]],
        operations_by_marker: dict[str, list[dict[str, Any]]],
        max_operation_payload_chars: int,
    ) -> str:
        lines = self._render_header(world_name, world_description, slot_title)
        lines.append(f"Total markers: {len(markers)}")
        lines.append("")
        if not markers:
            lines.append("No markers yet.")
        operation_total = 0
        for marker in markers:
            marker_ops = operations_by_marker.get(str(marker.get("id")), [])
            operation_total += len(marker_ops)
            marker_summary = _truncate_text(_normalize_text(marker.get("summary")), 300) or "-"
            when_text = _normalize_text(marker.get("date_label")) or f"sort_key={marker.get('sort_key')}"
            lines.append(
                f"- marker `{marker.get('id')}` | {marker.get('title')} | when={when_text} | "
                f"kind={marker.get('marker_kind')} | placement={marker.get('placement_status')}"
            )
            lines.append(f"  summary: {marker_summary}")
            if not marker_ops:
                lines.append("  operations: none")
                continue
            lines.append("  operations:")
            for operation in marker_ops:
                payload_raw = json.dumps(operation.get("payload", {}), ensure_ascii=True, sort_keys=True)
                payload_summary = _truncate_text(payload_raw, max_operation_payload_chars)
                lines.append(
                    f"  - {operation.get('op_type')} | target_kind={operation.get('target_kind')} "
                    f"| target_id={operation.get('target_id') or '-'} | op_id={operation.get('id')}"
                )
                lines.append(f"    payload: {payload_summary}")
        lines.append("")
        lines.append(f"Total operations in slot: {operation_total}")
        return "\n".join(lines).strip() + "\n"

    def _build_notes_doc(
        self,
        *,
        world_name: str,
        world_description: str,
        slot_title: str,
        notes: list[dict[str, Any]],
        max_note_excerpt_chars: int,
    ) -> str:
        lines = self._render_header(world_name, world_description, slot_title)
        lines.append(f"Total notes: {len(notes)}")
        lines.append("")
        if not notes:
            lines.append("No notes yet.")
        for note in notes:
            title = _normalize_text(note.get("title")) or "(untitled)"
            excerpt = _truncate_text(_normalize_text(note.get("content")), max_note_excerpt_chars) or "-"
            lines.append(
                f"- note `{note.get('id')}` | title={title} | status={note.get('status')} | "
                f"updated_at={note.get('updated_at')}"
            )
            lines.append(f"  excerpt: {excerpt}")
        return "\n".join(lines).strip() + "\n"

    def _build_rules_doc(
        self,
        *,
        world_name: str,
        world_description: str,
        world_entity_types: list[str],
        world_relation_types: list[str],
        entity_count: int,
        relation_count: int,
        marker_count: int,
        operation_count: int,
    ) -> str:
        lines = self._render_header(world_name, world_description, "Rules and Invariants")
        lines.append("This document stores explicit and derived canon constraints.")
        lines.append("")
        lines.append("## World taxonomies")
        lines.append(f"- entity_types: {', '.join(world_entity_types) if world_entity_types else 'none'}")
        lines.append(f"- relation_types: {', '.join(world_relation_types) if world_relation_types else 'none'}")
        lines.append("")
        lines.append("## Canon system constraints")
        lines.append("- timeline_marker_kind must be explicit or semantic")
        lines.append("- timeline_target_kind must be entity, relation, or world")
        lines.append("- timeline op types in this project: entity_create/entity_patch/entity_delete, relation_create/relation_patch/relation_delete, world_patch")
        lines.append("- relation endpoints must reference valid entity ids")
        lines.append("")
        lines.append("## Snapshot of current canonical volume")
        lines.append(f"- entities: {entity_count}")
        lines.append(f"- relations: {relation_count}")
        lines.append(f"- timeline_markers: {marker_count}")
        lines.append(f"- timeline_operations: {operation_count}")
        lines.append("")
        lines.append("## Recommended spare slots (not compiled yet)")
        for slot_key, slot_title in RECOMMENDED_SPARE_SLOT_KEYS:
            lines.append(f"- {slot_key}: {slot_title}")
        return "\n".join(lines).strip() + "\n"

    def _build_slot_payloads(
        self,
        *,
        world: dict[str, Any],
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        markers: list[dict[str, Any]],
        operations: list[dict[str, Any]],
        notes: list[dict[str, Any]],
        data: RagCompileRequest,
    ) -> list[_SlotContent]:
        world_name = _normalize_text(world.get("name")) or "Unknown World"
        world_description = _normalize_text(world.get("description"))
        world_entity_types = _load_json_list(world.get("entity_types"))
        world_relation_types = _load_json_list(world.get("relation_types"))

        entities_by_slot: dict[str, list[dict[str, Any]]] = {
            "characters": [],
            "locations": [],
            "organizations_factions": [],
            "items_artifacts_magic": [],
            "events": [],
        }
        for entity in entities:
            slot_key = self._entity_slot_key(entity)
            entities_by_slot.setdefault(slot_key, []).append(entity)

        character_relations = [
            relation
            for relation in relations
            if relation.get("source_type") == "character" or relation.get("target_type") == "character"
        ]
        spatial_relations = [relation for relation in relations if self._is_spatial_relation(relation)]

        operations_by_marker: dict[str, list[dict[str, Any]]] = {}
        for operation in operations:
            marker_id = str(operation.get("marker_id"))
            operations_by_marker.setdefault(marker_id, []).append(operation)

        timeline_by_slot = self._split_timeline(markers)
        notes_volumes = self._split_notes_into_volumes(notes, volume_count=5)

        built_slots: dict[str, _SlotContent] = {}
        built_slots["characters"] = _SlotContent(
            key="characters",
            title="Characters",
            content=self._build_entities_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Characters",
                entities=entities_by_slot.get("characters", []),
            ),
            record_count=len(entities_by_slot.get("characters", [])),
        )
        built_slots["locations"] = _SlotContent(
            key="locations",
            title="Locations",
            content=self._build_entities_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Locations",
                entities=entities_by_slot.get("locations", []),
            ),
            record_count=len(entities_by_slot.get("locations", [])),
        )
        built_slots["organizations_factions"] = _SlotContent(
            key="organizations_factions",
            title="Organizations and Factions",
            content=self._build_entities_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Organizations and Factions",
                entities=entities_by_slot.get("organizations_factions", []),
            ),
            record_count=len(entities_by_slot.get("organizations_factions", [])),
        )
        built_slots["items_artifacts_magic"] = _SlotContent(
            key="items_artifacts_magic",
            title="Items, Artifacts, and Magic",
            content=self._build_entities_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Items, Artifacts, and Magic",
                entities=entities_by_slot.get("items_artifacts_magic", []),
            ),
            record_count=len(entities_by_slot.get("items_artifacts_magic", [])),
        )
        built_slots["events"] = _SlotContent(
            key="events",
            title="Events",
            content=self._build_entities_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Events",
                entities=entities_by_slot.get("events", []),
            ),
            record_count=len(entities_by_slot.get("events", [])),
        )
        built_slots["relations_character"] = _SlotContent(
            key="relations_character",
            title="Character Relations",
            content=self._build_relations_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Character Relations",
                relations=character_relations,
            ),
            record_count=len(character_relations),
        )
        built_slots["relations_spatial"] = _SlotContent(
            key="relations_spatial",
            title="Spatial Relations",
            content=self._build_relations_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Spatial Relations",
                relations=spatial_relations,
            ),
            record_count=len(spatial_relations),
        )
        built_slots["timeline_ancient"] = _SlotContent(
            key="timeline_ancient",
            title="Timeline - Ancient",
            content=self._build_timeline_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Timeline - Ancient",
                markers=timeline_by_slot.get("timeline_ancient", []),
                operations_by_marker=operations_by_marker,
                max_operation_payload_chars=data.max_operation_payload_chars,
            ),
            record_count=len(timeline_by_slot.get("timeline_ancient", [])),
        )
        built_slots["timeline_past"] = _SlotContent(
            key="timeline_past",
            title="Timeline - Past",
            content=self._build_timeline_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Timeline - Past",
                markers=timeline_by_slot.get("timeline_past", []),
                operations_by_marker=operations_by_marker,
                max_operation_payload_chars=data.max_operation_payload_chars,
            ),
            record_count=len(timeline_by_slot.get("timeline_past", [])),
        )
        built_slots["timeline_present"] = _SlotContent(
            key="timeline_present",
            title="Timeline - Present",
            content=self._build_timeline_doc(
                world_name=world_name,
                world_description=world_description,
                slot_title="Timeline - Present",
                markers=timeline_by_slot.get("timeline_present", []),
                operations_by_marker=operations_by_marker,
                max_operation_payload_chars=data.max_operation_payload_chars,
            ),
            record_count=len(timeline_by_slot.get("timeline_present", [])),
        )

        for index, volume in enumerate(notes_volumes, start=1):
            slot_key = f"notes_lore_volume_{index}"
            slot_title = f"Notes Lore Volume {index}"
            built_slots[slot_key] = _SlotContent(
                key=slot_key,
                title=slot_title,
                content=self._build_notes_doc(
                    world_name=world_name,
                    world_description=world_description,
                    slot_title=slot_title,
                    notes=volume,
                    max_note_excerpt_chars=data.max_note_excerpt_chars,
                ),
                record_count=len(volume),
            )

        built_slots["rules_invariants"] = _SlotContent(
            key="rules_invariants",
            title="Rules and Invariants",
            content=self._build_rules_doc(
                world_name=world_name,
                world_description=world_description,
                world_entity_types=world_entity_types,
                world_relation_types=world_relation_types,
                entity_count=len(entities),
                relation_count=len(relations),
                marker_count=len(markers),
                operation_count=len(operations),
            ),
            record_count=1,
        )

        ordered_slots: list[_SlotContent] = []
        for slot_key, slot_title in RAG_SLOT_ORDER:
            slot = built_slots.get(slot_key)
            if slot:
                ordered_slots.append(slot)
            else:
                ordered_slots.append(
                    _SlotContent(
                        key=slot_key,
                        title=slot_title,
                        content=f"# {slot_title}\nNo data.\n",
                        record_count=0,
                    )
                )
        return ordered_slots

    async def compile_world_documents(self, world_id: str, data: RagCompileRequest) -> RagCompileResult:
        if not self.backboard.is_available:
            raise ValueError("Backboard service is not available")

        db = await self._get_db()
        try:
            world = await self._get_world(db, world_id)
            if not world:
                raise LookupError("World not found")
            assistant_id = _normalize_text(world.get("assistant_id"))
            if not assistant_id:
                raise ValueError(f"World {world_id} has no Backboard assistant configured")

            entities = await self._list_entities(db, world_id)
            relations = await self._list_relations(db, world_id)
            markers = await self._list_markers(db, world_id)
            operations = await self._list_operations(db, world_id)
            notes = await self._list_notes(db, world_id)
            existing_records = await self._slot_records(db, world_id)

            slot_payloads = self._build_slot_payloads(
                world=world,
                entities=entities,
                relations=relations,
                markers=markers,
                operations=operations,
                notes=notes,
                data=data,
            )

            slot_results: list[RagDocumentSyncStatusResult] = []
            created_count = 0
            updated_count = 0
            unchanged_count = 0
            skipped_count = 0
            failed_count = 0

            for slot in slot_payloads:
                rendered_content = slot.content
                if data.max_doc_chars > 0 and len(rendered_content) > data.max_doc_chars:
                    rendered_content = _truncate_text(rendered_content, data.max_doc_chars)
                content_hash = _hash_text(rendered_content)
                content_size = len(rendered_content)
                existing = existing_records.get(slot.key)
                existing_doc_id = _normalize_text(existing.get("document_id")) if existing else ""

                if not data.include_empty_slots and slot.record_count == 0:
                    skipped_count += 1
                    slot_results.append(
                        RagDocumentSyncStatusResult(
                            slot_key=slot.key,
                            slot_title=slot.title,
                            sync_status="skipped",
                            document_id=existing_doc_id or None,
                            content_hash=content_hash,
                            content_size=content_size,
                            record_count=slot.record_count,
                        )
                    )
                    continue

                if data.dry_run:
                    slot_results.append(
                        RagDocumentSyncStatusResult(
                            slot_key=slot.key,
                            slot_title=slot.title,
                            sync_status="dry_run",
                            document_id=existing_doc_id or None,
                            content_hash=content_hash,
                            content_size=content_size,
                            record_count=slot.record_count,
                        )
                    )
                    continue

                if (
                    existing
                    and not data.force_upload
                    and _normalize_text(existing.get("content_hash")) == content_hash
                    and existing_doc_id
                ):
                    unchanged_count += 1
                    await self._upsert_slot_record(
                        db,
                        world_id=world_id,
                        assistant_id=assistant_id,
                        slot_key=slot.key,
                        slot_title=slot.title,
                        document_id=existing_doc_id,
                        content_hash=content_hash,
                        content_size=content_size,
                        record_count=slot.record_count,
                    )
                    slot_results.append(
                        RagDocumentSyncStatusResult(
                            slot_key=slot.key,
                            slot_title=slot.title,
                            sync_status="unchanged",
                            document_id=existing_doc_id,
                            content_hash=content_hash,
                            content_size=content_size,
                            record_count=slot.record_count,
                        )
                    )
                    continue

                sync_status = "created"
                resolved_document_id: str | None = None
                error_message: str | None = None
                try:
                    if existing_doc_id:
                        sync_status = "updated"
                        update_result = await self.backboard.update_lore_document(
                            assistant_id=assistant_id,
                            document_id=existing_doc_id,
                            document_type=self._slot_document_type(slot.key),
                            content=rendered_content,
                        )
                        if update_result.success and update_result.id:
                            resolved_document_id = update_result.id
                        else:
                            create_result = await self.backboard.create_lore_document(
                                assistant_id=assistant_id,
                                document_type=self._slot_document_type(slot.key),
                                content=rendered_content,
                            )
                            if create_result.success and create_result.id:
                                resolved_document_id = create_result.id
                            else:
                                error_message = "Backboard update/create failed"
                    else:
                        create_result = await self.backboard.create_lore_document(
                            assistant_id=assistant_id,
                            document_type=self._slot_document_type(slot.key),
                            content=rendered_content,
                        )
                        if create_result.success and create_result.id:
                            resolved_document_id = create_result.id
                        else:
                            error_message = "Backboard create failed"
                except Exception as error:
                    error_message = str(error)

                if not resolved_document_id:
                    failed_count += 1
                    slot_results.append(
                        RagDocumentSyncStatusResult(
                            slot_key=slot.key,
                            slot_title=slot.title,
                            sync_status="failed",
                            document_id=existing_doc_id or None,
                            content_hash=content_hash,
                            content_size=content_size,
                            record_count=slot.record_count,
                            error=error_message or "Unknown sync error",
                        )
                    )
                    continue

                if sync_status == "created":
                    created_count += 1
                else:
                    updated_count += 1

                await self._upsert_slot_record(
                    db,
                    world_id=world_id,
                    assistant_id=assistant_id,
                    slot_key=slot.key,
                    slot_title=slot.title,
                    document_id=resolved_document_id,
                    content_hash=content_hash,
                    content_size=content_size,
                    record_count=slot.record_count,
                )
                slot_results.append(
                    RagDocumentSyncStatusResult(
                        slot_key=slot.key,
                        slot_title=slot.title,
                        sync_status=sync_status,  # type: ignore[arg-type]
                        document_id=resolved_document_id,
                        content_hash=content_hash,
                        content_size=content_size,
                        record_count=slot.record_count,
                    )
                )

            total_slots = len(slot_payloads)
            processed_slots = created_count + updated_count + unchanged_count + skipped_count + failed_count
            if data.dry_run:
                status = "dry_run"
            elif failed_count > 0:
                status = "partial"
            else:
                status = "completed"

            logger.info(
                "[RAG][compile] world_id=%s status=%s created=%d updated=%d unchanged=%d skipped=%d failed=%d",
                world_id,
                status,
                created_count,
                updated_count,
                unchanged_count,
                skipped_count,
                failed_count,
            )

            return RagCompileResult(
                status=status,
                world_id=world_id,
                assistant_id=assistant_id,
                total_slots=total_slots,
                processed_slots=processed_slots,
                created_count=created_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                slots=slot_results,
                message="World RAG compilation finished",
            )
        finally:
            await db.close()
