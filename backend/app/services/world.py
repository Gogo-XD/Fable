"""
World management service.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

from app.logging import get_logger
from app.models import World, WorldCreate, WorldUpdate
from app.services.backboard import BackboardService

logger = get_logger('services.world')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_world(row: dict) -> World:
    return World(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        assistant_id=row.get("assistant_id"),
        entity_types=json.loads(row["entity_types"]),
        relation_types=json.loads(row["relation_types"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class WorldService:
    """Service for world CRUD and assistant provisioning."""

    def __init__(self, db_path: str, backboard: BackboardService):
        self.db_path = db_path
        self.backboard = backboard

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def list_worlds(self) -> list[World]:
        db = await self._get_db()
        try:
            cursor = await db.execute("SELECT * FROM worlds ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [_row_to_world(dict(r)) for r in rows]
        finally:
            await db.close()

    async def get_world(self, world_id: str) -> World | None:
        db = await self._get_db()
        try:
            cursor = await db.execute("SELECT * FROM worlds WHERE id = ?", (world_id,))
            row = await cursor.fetchone()
            return _row_to_world(dict(row)) if row else None
        finally:
            await db.close()

    async def create_world(self, data: WorldCreate) -> World:
        now = _now()
        world_id = str(uuid4())

        # Create a Backboard assistant for this world
        assistant_id = None
        if self.backboard.is_available:
            result = await self.backboard.create_world_assistant(
                data.name, data.description or ""
            )
            if result.success:
                assistant_id = result.id

        world = World(
            id=world_id,
            name=data.name,
            description=data.description,
            assistant_id=assistant_id,
            entity_types=data.entity_types,
            relation_types=data.relation_types,
            created_at=now,
            updated_at=now,
        )

        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO worlds (id, name, description, assistant_id, entity_types, relation_types, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (world.id, world.name, world.description, world.assistant_id,
                 json.dumps(world.entity_types), json.dumps(world.relation_types),
                 world.created_at, world.updated_at),
            )
            await db.commit()
        finally:
            await db.close()

        logger.info(f"Created world: {world.name} ({world.id[:8]})")
        return world

    async def update_world(self, world_id: str, data: WorldUpdate) -> World | None:
        existing = await self.get_world(world_id)
        if not existing:
            return None

        fields: dict = {}
        if data.name is not None:
            fields["name"] = data.name
        if data.description is not None:
            fields["description"] = data.description
        if data.entity_types is not None:
            fields["entity_types"] = json.dumps(data.entity_types)
        if data.relation_types is not None:
            fields["relation_types"] = json.dumps(data.relation_types)

        if not fields:
            return existing

        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [world_id]

        db = await self._get_db()
        try:
            await db.execute(f"UPDATE worlds SET {set_clause} WHERE id = ?", params)
            await db.commit()
        finally:
            await db.close()

        return await self.get_world(world_id)

    async def delete_world(self, world_id: str) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute("DELETE FROM worlds WHERE id = ?", (world_id,))
            await db.commit()
            deleted = cursor.rowcount > 0
        finally:
            await db.close()

        if deleted:
            logger.info(f"Deleted world {world_id[:8]} and all associated data")
        return deleted
