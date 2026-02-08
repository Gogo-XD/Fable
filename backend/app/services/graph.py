"""Graph service for graph retrieval and filtering."""

import json

import aiosqlite

from app.models import Entity, Relation, normalize_type


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


class GraphService:
    """Business logic for world graph retrieval and filtering."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def get_graph(
        self,
        world_id: str,
        entity_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        focus_entity_id: str | None = None,
    ) -> dict:
        entity_type_filters = [normalize_type(t) for t in entity_types] if entity_types else None
        relation_type_filters = [normalize_type(t) for t in relation_types] if relation_types else None

        entities = await self._list_entities(world_id, entity_type_filters)
        entity_ids = {e.id for e in entities}
        relations = await self._list_relations(world_id, relation_type_filters, entity_ids)

        if focus_entity_id:
            focus_relations = [
                r for r in relations
                if r.source_entity_id == focus_entity_id or r.target_entity_id == focus_entity_id
            ]
            connected_ids = {focus_entity_id}
            for rel in focus_relations:
                connected_ids.add(rel.source_entity_id)
                connected_ids.add(rel.target_entity_id)
            entities = [e for e in entities if e.id in connected_ids]
            relations = focus_relations

        return {
            "entities": [e.model_dump() for e in entities],
            "relations": [r.model_dump() for r in relations],
        }

    async def _list_entities(self, world_id: str, entity_types: list[str] | None = None) -> list[Entity]:
        conditions = ["world_id = ?"]
        params: list[str] = [world_id]
        if entity_types:
            placeholders = ", ".join("?" for _ in entity_types)
            conditions.append(f"type IN ({placeholders})")
            params.extend(entity_types)

        query = f"SELECT * FROM entities WHERE {' AND '.join(conditions)} ORDER BY name"
        db = await self._get_db()
        try:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [_row_to_entity(dict(r)) for r in rows]
        finally:
            await db.close()

    async def _list_relations(
        self,
        world_id: str,
        relation_types: list[str] | None = None,
        entity_ids: set[str] | None = None,
    ) -> list[Relation]:
        conditions = ["world_id = ?"]
        params: list[str] = [world_id]

        if relation_types:
            placeholders = ", ".join("?" for _ in relation_types)
            conditions.append(f"type IN ({placeholders})")
            params.extend(relation_types)

        query = f"SELECT * FROM relations WHERE {' AND '.join(conditions)} ORDER BY created_at"
        db = await self._get_db()
        try:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            relations = [_row_to_relation(dict(r)) for r in rows]
        finally:
            await db.close()

        if entity_ids is None:
            return relations
        return [
            r for r in relations
            if r.source_entity_id in entity_ids and r.target_entity_id in entity_ids
        ]
