"""Relation operations."""

from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from app.models import Relation, RelationCreate, RelationUpdate, EntitySource, normalize_type


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_relation(row: dict) -> Relation:
    return Relation(
        id=row["id"],
        world_id=row["world_id"],
        source_entity_id=row["source_entity_id"],
        target_entity_id=row["target_entity_id"],
        type=row["type"],
        context=row.get("context"),
        weight=row["weight"],
        source=row["source"],
        source_note_id=row.get("source_note_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class LoreRelationService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def create_relation(self, world_id: str, data: RelationCreate) -> Relation:
        now = _now()
        relation = Relation(
            id=str(uuid4()),
            world_id=world_id,
            source_entity_id=data.source_entity_id,
            target_entity_id=data.target_entity_id,
            type=normalize_type(data.type),
            context=data.context,
            weight=data.weight,
            source=EntitySource.USER,
            created_at=now,
            updated_at=now,
        )
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO relations
                   (id, world_id, source_entity_id, target_entity_id, type, context, weight, source, source_note_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    relation.id,
                    relation.world_id,
                    relation.source_entity_id,
                    relation.target_entity_id,
                    relation.type,
                    relation.context,
                    relation.weight,
                    relation.source.value,
                    relation.source_note_id,
                    relation.created_at,
                    relation.updated_at,
                ),
            )
            await db.commit()
        finally:
            await db.close()
        return relation

    async def create_ai_relation(
        self,
        world_id: str,
        note_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        context: str | None,
        weight: float = 0.5,
    ) -> str:
        now = _now()
        relation_id = str(uuid4())
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO relations
                   (id, world_id, source_entity_id, target_entity_id, type, context, weight, source, source_note_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    relation_id,
                    world_id,
                    source_id,
                    target_id,
                    normalize_type(relation_type),
                    context,
                    weight,
                    EntitySource.AI.value,
                    note_id,
                    now,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()
        return relation_id

    async def relation_exists(
        self,
        world_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT id FROM relations
                   WHERE world_id = ? AND source_entity_id = ? AND target_entity_id = ? AND type = ?""",
                (world_id, source_id, target_id, normalize_type(relation_type)),
            )
            return (await cursor.fetchone()) is not None
        finally:
            await db.close()

    async def get_relation(self, world_id: str, relation_id: str) -> Relation | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM relations WHERE id = ? AND world_id = ?",
                (relation_id, world_id),
            )
            row = await cursor.fetchone()
            return _row_to_relation(dict(row)) if row else None
        finally:
            await db.close()

    async def list_relations(
        self,
        world_id: str,
        entity_id: str | None = None,
        type: str | None = None,
    ) -> list[Relation]:
        conditions = ["world_id = ?"]
        params: list = [world_id]
        if entity_id:
            conditions.append("(source_entity_id = ? OR target_entity_id = ?)")
            params.extend([entity_id, entity_id])
        if type:
            conditions.append("type = ?")
            params.append(normalize_type(type))
        query = f"SELECT * FROM relations WHERE {' AND '.join(conditions)} ORDER BY created_at"
        db = await self._get_db()
        try:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [_row_to_relation(dict(r)) for r in rows]
        finally:
            await db.close()

    async def update_relation(
        self, world_id: str, relation_id: str, data: RelationUpdate
    ) -> Relation | None:
        existing = await self.get_relation(world_id, relation_id)
        if not existing:
            return None
        fields: dict = {}
        if data.type is not None:
            fields["type"] = normalize_type(data.type)
        if data.context is not None:
            fields["context"] = data.context
        if data.weight is not None:
            fields["weight"] = data.weight
        if not fields:
            return existing
        fields["source"] = EntitySource.USER.value
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [relation_id, world_id]
        db = await self._get_db()
        try:
            await db.execute(
                f"UPDATE relations SET {set_clause} WHERE id = ? AND world_id = ?",
                params,
            )
            await db.commit()
        finally:
            await db.close()
        return await self.get_relation(world_id, relation_id)

    async def delete_relation(self, world_id: str, relation_id: str) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "DELETE FROM relations WHERE id = ? AND world_id = ?",
                (relation_id, world_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()
