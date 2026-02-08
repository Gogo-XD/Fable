"""Entity operations and entity-context merge helpers."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from app.logging import get_logger
from app.models import (
    Entity,
    EntityCreate,
    EntityUpdate,
    EntitySource,
    EntityExtraction,
    normalize_type,
)
from app.services.backboard import BackboardService
from app.services.prompts import build_context_merge_prompt

logger = get_logger("services.lore_entities")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_entity(row: dict) -> Entity:
    return Entity(
        id=row["id"],
        world_id=row["world_id"],
        name=row["name"],
        type=row["type"],
        subtype=row.get("subtype"),
        aliases=json.loads(row["aliases"]),
        context=row.get("context"),
        summary=row.get("summary"),
        tags=json.loads(row["tags"]),
        image_url=row.get("image_url"),
        status=row.get("status", "active"),
        source=row["source"],
        source_note_id=row.get("source_note_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class LoreEntityService:
    def __init__(self, db_path: str, backboard: BackboardService):
        self.db_path = db_path
        self.backboard = backboard

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def get_world_assistant_id(self, world_id: str) -> str | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT assistant_id FROM worlds WHERE id = ?",
                (world_id,),
            )
            row = await cursor.fetchone()
            return dict(row)["assistant_id"] if row else None
        finally:
            await db.close()

    async def create_entity(self, world_id: str, data: EntityCreate) -> Entity:
        now = _now()
        entity = Entity(
            id=str(uuid4()),
            world_id=world_id,
            name=data.name,
            type=normalize_type(data.type),
            subtype=normalize_type(data.subtype) if data.subtype else None,
            aliases=data.aliases,
            context=data.context,
            summary=data.summary,
            tags=data.tags,
            image_url=data.image_url,
            status=data.status,
            source=EntitySource.USER,
            created_at=now,
            updated_at=now,
        )
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO entities
                   (id, world_id, name, type, subtype, aliases, context, summary, tags, image_url, status, source, source_note_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity.id,
                    entity.world_id,
                    entity.name,
                    entity.type,
                    entity.subtype,
                    json.dumps(entity.aliases),
                    entity.context,
                    entity.summary,
                    json.dumps(entity.tags),
                    entity.image_url,
                    entity.status,
                    entity.source.value,
                    entity.source_note_id,
                    entity.created_at,
                    entity.updated_at,
                ),
            )
            await db.commit()
        finally:
            await db.close()
        return entity

    async def create_ai_entity(
        self, world_id: str, note_id: str, extracted: EntityExtraction
    ) -> str:
        now = _now()
        entity_id = str(uuid4())
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO entities
                   (id, world_id, name, type, subtype, aliases, context, summary, tags, image_url, status, source, source_note_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity_id,
                    world_id,
                    extracted.name,
                    extracted.type,
                    extracted.subtype,
                    json.dumps(extracted.aliases),
                    extracted.context,
                    extracted.summary,
                    json.dumps(extracted.tags),
                    None,
                    "active",
                    EntitySource.AI.value,
                    note_id,
                    now,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()
        return entity_id

    async def update_merged_entity_fields(
        self,
        world_id: str,
        entity_id: str,
        merged_aliases: list[str],
        merged_tags: list[str],
        merged_context: str | None,
        merged_summary: str | None,
    ) -> None:
        db = await self._get_db()
        try:
            await db.execute(
                """UPDATE entities SET aliases = ?, tags = ?, context = ?, summary = ?, updated_at = ?
                   WHERE id = ? AND world_id = ?""",
                (
                    json.dumps(merged_aliases),
                    json.dumps(merged_tags),
                    merged_context,
                    merged_summary,
                    _now(),
                    entity_id,
                    world_id,
                ),
            )
            await db.commit()
        finally:
            await db.close()

    async def get_entity(self, world_id: str, entity_id: str) -> Entity | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM entities WHERE id = ? AND world_id = ?",
                (entity_id, world_id),
            )
            row = await cursor.fetchone()
            return _row_to_entity(dict(row)) if row else None
        finally:
            await db.close()

    async def list_entities(
        self,
        world_id: str,
        type: str | None = None,
        subtype: str | None = None,
        tag: str | None = None,
        search: str | None = None,
    ) -> list[Entity]:
        conditions = ["world_id = ?"]
        params: list = [world_id]
        if type:
            conditions.append("type = ?")
            params.append(normalize_type(type))
        if subtype:
            conditions.append("subtype = ?")
            params.append(normalize_type(subtype))
        if search:
            conditions.append("(name LIKE ? OR aliases LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        query = f"SELECT * FROM entities WHERE {' AND '.join(conditions)} ORDER BY name"
        db = await self._get_db()
        try:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            entities = [_row_to_entity(dict(r)) for r in rows]
        finally:
            await db.close()
        if tag:
            entities = [e for e in entities if tag in e.tags]
        return entities

    async def update_entity(
        self, world_id: str, entity_id: str, data: EntityUpdate
    ) -> Entity | None:
        existing = await self.get_entity(world_id, entity_id)
        if not existing:
            return None
        fields: dict = {}
        if data.name is not None:
            fields["name"] = data.name
        if data.type is not None:
            fields["type"] = normalize_type(data.type)
        if data.subtype is not None:
            fields["subtype"] = normalize_type(data.subtype)
        if data.aliases is not None:
            fields["aliases"] = json.dumps(data.aliases)
        if data.context is not None:
            fields["context"] = data.context
        if data.summary is not None:
            fields["summary"] = data.summary
        if data.tags is not None:
            fields["tags"] = json.dumps(data.tags)
        if data.image_url is not None:
            fields["image_url"] = data.image_url
        if data.status is not None:
            fields["status"] = data.status
        if not fields:
            return existing
        fields["source"] = EntitySource.USER.value
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [entity_id, world_id]
        db = await self._get_db()
        try:
            await db.execute(
                f"UPDATE entities SET {set_clause} WHERE id = ? AND world_id = ?",
                params,
            )
            await db.commit()
        finally:
            await db.close()
        return await self.get_entity(world_id, entity_id)

    async def delete_entity(self, world_id: str, entity_id: str) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "DELETE FROM entities WHERE id = ? AND world_id = ?",
                (entity_id, world_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def merge_entity_context_with_llm(
        self,
        world_id: str,
        entity_name: str,
        entity_type: str,
        existing_context: str | None,
        incoming_context: str | None,
    ) -> str | None:
        if not existing_context and not incoming_context:
            return None
        if not self.backboard.is_available:
            return incoming_context or existing_context
        assistant_id = await self.get_world_assistant_id(world_id)
        if not assistant_id:
            return incoming_context or existing_context
        thread_id: str | None = None
        try:
            thread_result = await self.backboard.create_thread(assistant_id)
            if not thread_result.success or not thread_result.id:
                return incoming_context or existing_context
            thread_id = thread_result.id
            prompt = build_context_merge_prompt(
                entity_name=entity_name,
                entity_type=entity_type,
                existing_context=existing_context,
                incoming_context=incoming_context,
            )
            chat_result = await self.backboard.chat(thread_id=thread_id, prompt=prompt, memory="off")
            if not chat_result.success or not chat_result.response:
                return incoming_context or existing_context
            merged = chat_result.response.strip()
            if merged.startswith("```"):
                merged = merged.strip("`").strip()
                if merged.lower().startswith("text"):
                    merged = merged[4:].strip()
            return merged or incoming_context or existing_context
        except Exception as e:
            logger.warning(f"LLM context merge failed for entity '{entity_name}': {e}")
            return incoming_context or existing_context
        finally:
            if thread_id:
                try:
                    await self.backboard.delete_thread(thread_id)
                except Exception:
                    pass

