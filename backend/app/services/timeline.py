"""Timeline service for marker, operation, snapshot, and projection workflows."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import aiosqlite

from app.models import (
    Entity,
    Relation,
    TimelineMarker,
    TimelineMarkerCreate,
    TimelineMarkerReposition,
    TimelineRebuildResult,
    TimelineMarkerUpdate,
    TimelineOperation,
    TimelineOperationCreate,
    TimelineOperationUpdate,
    TimelineSnapshot,
    TimelineSnapshotUpsert,
    TimelineWorldState,
    normalize_type,
)

VALID_MARKER_KINDS = {"explicit", "semantic"}
VALID_PLACEMENT_STATUSES = {"placed", "unplaced"}
VALID_TARGET_KINDS = {"entity", "relation", "world"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_marker_kind(kind: str) -> str:
    normalized = normalize_type(kind)
    if normalized not in VALID_MARKER_KINDS:
        raise ValueError("marker_kind must be one of: explicit, semantic")
    return normalized


def _normalize_placement_status(status: str) -> str:
    normalized = normalize_type(status)
    if normalized not in VALID_PLACEMENT_STATUSES:
        raise ValueError("placement_status must be one of: placed, unplaced")
    return normalized


def _normalize_target_kind(kind: str) -> str:
    normalized = normalize_type(kind)
    if normalized not in VALID_TARGET_KINDS:
        raise ValueError("target_kind must be one of: entity, relation, world")
    return normalized


def _load_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _row_to_marker(row: dict) -> TimelineMarker:
    return TimelineMarker(
        id=row["id"],
        world_id=row["world_id"],
        title=row["title"],
        summary=row.get("summary"),
        marker_kind=row["marker_kind"],
        placement_status=row["placement_status"],
        date_label=row.get("date_label"),
        date_sort_value=row.get("date_sort_value"),
        sort_key=row["sort_key"],
        source=row["source"],
        source_note_id=row.get("source_note_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_operation(row: dict) -> TimelineOperation:
    return TimelineOperation(
        id=row["id"],
        world_id=row["world_id"],
        marker_id=row["marker_id"],
        op_type=row["op_type"],
        target_kind=row["target_kind"],
        target_id=row.get("target_id"),
        payload=_load_json(row.get("payload"), {}),
        order_index=row["order_index"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_snapshot(row: dict) -> TimelineSnapshot:
    return TimelineSnapshot(
        id=row["id"],
        world_id=row["world_id"],
        marker_id=row["marker_id"],
        state_json=_load_json(row.get("state_json"), {}),
        state_hash=row.get("state_hash"),
        applied_marker_count=row["applied_marker_count"],
        entity_count=row["entity_count"],
        relation_count=row["relation_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_entity(row: dict) -> Entity:
    return Entity(
        id=row["id"],
        world_id=row["world_id"],
        name=row["name"],
        type=row["type"],
        subtype=row.get("subtype"),
        aliases=_load_json(row.get("aliases"), []),
        context=row.get("context"),
        summary=row.get("summary"),
        tags=_load_json(row.get("tags"), []),
        image_url=row.get("image_url"),
        status=row.get("status", "active"),
        exists_at_marker=bool(row.get("exists_at_marker", True)),
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
        exists_at_marker=bool(row.get("exists_at_marker", True)),
        source=row["source"],
        source_note_id=row.get("source_note_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class TimelineService:
    """Timeline-oriented data access and world-state projection service."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _next_sort_key(self, db: aiosqlite.Connection, world_id: str) -> float:
        cursor = await db.execute(
            "SELECT COALESCE(MAX(sort_key), 0) + 1 AS next_key FROM timeline_markers WHERE world_id = ?",
            (world_id,),
        )
        row = await cursor.fetchone()
        return float(row["next_key"] if row else 1.0)

    async def _marker_sort_key(
        self,
        db: aiosqlite.Connection,
        world_id: str,
        marker_id: str,
    ) -> float | None:
        cursor = await db.execute(
            "SELECT sort_key FROM timeline_markers WHERE world_id = ? AND id = ?",
            (world_id, marker_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return float(row["sort_key"])

    async def list_markers(
        self,
        world_id: str,
        include_operations: bool = False,
    ) -> list[TimelineMarker]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT * FROM timeline_markers
                   WHERE world_id = ?
                   ORDER BY sort_key ASC, created_at ASC, id ASC""",
                (world_id,),
            )
            rows = await cursor.fetchall()
            markers = [_row_to_marker(dict(row)) for row in rows]

            if not include_operations or not markers:
                return markers

            marker_ids = [m.id for m in markers]
            placeholders = ", ".join("?" for _ in marker_ids)
            op_cursor = await db.execute(
                f"""SELECT * FROM timeline_operations
                    WHERE world_id = ? AND marker_id IN ({placeholders})
                    ORDER BY marker_id ASC, order_index ASC, created_at ASC, id ASC""",
                [world_id, *marker_ids],
            )
            op_rows = await op_cursor.fetchall()

            ops_by_marker: dict[str, list[TimelineOperation]] = {m.id: [] for m in markers}
            for row in op_rows:
                op = _row_to_operation(dict(row))
                ops_by_marker.setdefault(op.marker_id, []).append(op)
            for marker in markers:
                marker.operations = ops_by_marker.get(marker.id, [])
            return markers
        finally:
            await db.close()

    async def get_marker(
        self,
        world_id: str,
        marker_id: str,
        include_operations: bool = True,
    ) -> TimelineMarker | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM timeline_markers WHERE world_id = ? AND id = ?",
                (world_id, marker_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            marker = _row_to_marker(dict(row))
            if include_operations:
                marker.operations = await self.list_operations(world_id, marker_id)
            return marker
        finally:
            await db.close()

    async def create_marker(
        self,
        world_id: str,
        data: TimelineMarkerCreate,
        rebuild_snapshots: bool = True,
    ) -> TimelineMarker:
        now = _now()
        marker_id = str(uuid4())
        marker_kind = _normalize_marker_kind(data.marker_kind)
        placement_status = _normalize_placement_status(data.placement_status)

        db = await self._get_db()
        try:
            sort_key = data.sort_key

            # Semantic markers default to end-of-timeline placement until manually positioned.
            if marker_kind == "semantic" and sort_key is None:
                placement_status = "unplaced"

            if sort_key is None:
                if marker_kind == "explicit" and data.date_sort_value is not None:
                    sort_key = float(data.date_sort_value)
                else:
                    sort_key = await self._next_sort_key(db, world_id)

            await db.execute(
                """INSERT INTO timeline_markers
                   (id, world_id, title, summary, marker_kind, placement_status, date_label, date_sort_value, sort_key, source, source_note_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    marker_id,
                    world_id,
                    data.title,
                    data.summary,
                    marker_kind,
                    placement_status,
                    data.date_label,
                    data.date_sort_value,
                    float(sort_key),
                    data.source.value,
                    data.source_note_id,
                    now,
                    now,
                ),
            )

            for index, operation in enumerate(data.operations):
                target_kind = _normalize_target_kind(operation.target_kind)
                await db.execute(
                    """INSERT INTO timeline_operations
                       (id, world_id, marker_id, op_type, target_kind, target_id, payload, order_index, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid4()),
                        world_id,
                        marker_id,
                        normalize_type(operation.op_type),
                        target_kind,
                        operation.target_id,
                        json.dumps(operation.payload),
                        operation.order_index if operation.order_index is not None else index,
                        now,
                        now,
                    ),
                )

            await db.commit()
        finally:
            await db.close()

        marker = await self.get_marker(world_id, marker_id, include_operations=True)
        if not marker:
            raise ValueError("Failed to create timeline marker")
        if rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return marker

    async def update_marker(
        self,
        world_id: str,
        marker_id: str,
        data: TimelineMarkerUpdate,
        rebuild_snapshots: bool = True,
    ) -> TimelineMarker | None:
        existing = await self.get_marker(world_id, marker_id, include_operations=False)
        if not existing:
            return None

        fields: dict[str, Any] = {}
        if data.title is not None:
            fields["title"] = data.title
        if data.summary is not None:
            fields["summary"] = data.summary
        if data.marker_kind is not None:
            fields["marker_kind"] = _normalize_marker_kind(data.marker_kind)
        if data.placement_status is not None:
            fields["placement_status"] = _normalize_placement_status(data.placement_status)
        if data.date_label is not None:
            fields["date_label"] = data.date_label
        if data.date_sort_value is not None:
            fields["date_sort_value"] = data.date_sort_value
        if data.sort_key is not None:
            fields["sort_key"] = float(data.sort_key)
        if data.source_note_id is not None:
            fields["source_note_id"] = data.source_note_id

        if not fields:
            return await self.get_marker(world_id, marker_id, include_operations=True)

        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        params = list(fields.values()) + [world_id, marker_id]

        db = await self._get_db()
        try:
            await db.execute(
                f"UPDATE timeline_markers SET {set_clause} WHERE world_id = ? AND id = ?",
                params,
            )
            await db.commit()
        finally:
            await db.close()

        marker = await self.get_marker(world_id, marker_id, include_operations=True)
        if marker and rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return marker

    async def reposition_marker(
        self,
        world_id: str,
        marker_id: str,
        data: TimelineMarkerReposition,
        rebuild_snapshots: bool = True,
    ) -> TimelineMarker | None:
        placement_status = _normalize_placement_status(data.placement_status)
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """UPDATE timeline_markers
                   SET sort_key = ?, placement_status = ?, updated_at = ?
                   WHERE world_id = ? AND id = ?""",
                (float(data.sort_key), placement_status, _now(), world_id, marker_id),
            )
            await db.commit()
            if cursor.rowcount <= 0:
                return None
        finally:
            await db.close()

        marker = await self.get_marker(world_id, marker_id, include_operations=True)
        if marker and rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return marker

    async def delete_marker(
        self,
        world_id: str,
        marker_id: str,
        rebuild_snapshots: bool = True,
    ) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "DELETE FROM timeline_markers WHERE world_id = ? AND id = ?",
                (world_id, marker_id),
            )
            await db.commit()
            deleted = cursor.rowcount > 0
        finally:
            await db.close()
        if deleted and rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return deleted

    async def list_operations(self, world_id: str, marker_id: str) -> list[TimelineOperation]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT * FROM timeline_operations
                   WHERE world_id = ? AND marker_id = ?
                   ORDER BY order_index ASC, created_at ASC, id ASC""",
                (world_id, marker_id),
            )
            rows = await cursor.fetchall()
            return [_row_to_operation(dict(row)) for row in rows]
        finally:
            await db.close()

    async def _get_operation(
        self,
        world_id: str,
        marker_id: str,
        operation_id: str,
    ) -> TimelineOperation | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT * FROM timeline_operations
                   WHERE world_id = ? AND marker_id = ? AND id = ?""",
                (world_id, marker_id, operation_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_operation(dict(row))
        finally:
            await db.close()

    async def create_operation(
        self,
        world_id: str,
        marker_id: str,
        data: TimelineOperationCreate,
        rebuild_snapshots: bool = True,
    ) -> TimelineOperation | None:
        marker = await self.get_marker(world_id, marker_id, include_operations=False)
        if not marker:
            return None

        operation_id = str(uuid4())
        now = _now()
        target_kind = _normalize_target_kind(data.target_kind)
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO timeline_operations
                   (id, world_id, marker_id, op_type, target_kind, target_id, payload, order_index, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    operation_id,
                    world_id,
                    marker_id,
                    normalize_type(data.op_type),
                    target_kind,
                    data.target_id,
                    json.dumps(data.payload),
                    data.order_index,
                    now,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()

        operation = await self._get_operation(world_id, marker_id, operation_id)
        if operation and rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return operation

    async def update_operation(
        self,
        world_id: str,
        marker_id: str,
        operation_id: str,
        data: TimelineOperationUpdate,
        rebuild_snapshots: bool = True,
    ) -> TimelineOperation | None:
        existing = await self._get_operation(world_id, marker_id, operation_id)
        if not existing:
            return None

        fields: dict[str, Any] = {}
        if data.op_type is not None:
            fields["op_type"] = normalize_type(data.op_type)
        if data.target_kind is not None:
            fields["target_kind"] = _normalize_target_kind(data.target_kind)
        if data.target_id is not None:
            fields["target_id"] = data.target_id
        if data.payload is not None:
            fields["payload"] = json.dumps(data.payload)
        if data.order_index is not None:
            fields["order_index"] = data.order_index

        if not fields:
            return existing

        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        params = list(fields.values()) + [world_id, marker_id, operation_id]

        db = await self._get_db()
        try:
            await db.execute(
                f"""UPDATE timeline_operations
                    SET {set_clause}
                    WHERE world_id = ? AND marker_id = ? AND id = ?""",
                params,
            )
            await db.commit()
        finally:
            await db.close()

        operation = await self._get_operation(world_id, marker_id, operation_id)
        if operation and rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return operation

    async def delete_operation(
        self,
        world_id: str,
        marker_id: str,
        operation_id: str,
        rebuild_snapshots: bool = True,
    ) -> bool:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """DELETE FROM timeline_operations
                   WHERE world_id = ? AND marker_id = ? AND id = ?""",
                (world_id, marker_id, operation_id),
            )
            await db.commit()
            deleted = cursor.rowcount > 0
        finally:
            await db.close()
        if deleted and rebuild_snapshots:
            await self.rebuild_snapshots(world_id)
        return deleted

    async def list_snapshots(self, world_id: str) -> list[TimelineSnapshot]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT * FROM timeline_snapshots
                   WHERE world_id = ?
                   ORDER BY updated_at DESC, created_at DESC""",
                (world_id,),
            )
            rows = await cursor.fetchall()
            return [_row_to_snapshot(dict(row)) for row in rows]
        finally:
            await db.close()

    async def get_snapshot(self, world_id: str, marker_id: str) -> TimelineSnapshot | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT * FROM timeline_snapshots
                   WHERE world_id = ? AND marker_id = ?""",
                (world_id, marker_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_snapshot(dict(row))
        finally:
            await db.close()

    async def upsert_snapshot(
        self,
        world_id: str,
        marker_id: str,
        data: TimelineSnapshotUpsert,
    ) -> TimelineSnapshot:
        now = _now()
        snapshot_id = str(uuid4())
        db = await self._get_db()
        try:
            await db.execute(
                """INSERT INTO timeline_snapshots
                   (id, world_id, marker_id, state_json, state_hash, applied_marker_count, entity_count, relation_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(world_id, marker_id) DO UPDATE SET
                       state_json = excluded.state_json,
                       state_hash = excluded.state_hash,
                       applied_marker_count = excluded.applied_marker_count,
                       entity_count = excluded.entity_count,
                       relation_count = excluded.relation_count,
                       updated_at = excluded.updated_at""",
                (
                    snapshot_id,
                    world_id,
                    marker_id,
                    json.dumps(data.state_json),
                    data.state_hash,
                    data.applied_marker_count,
                    data.entity_count,
                    data.relation_count,
                    now,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()

        snapshot = await self.get_snapshot(world_id, marker_id)
        if not snapshot:
            raise ValueError("Failed to upsert timeline snapshot")
        return snapshot

    def _state_json_from_world_state(self, state: TimelineWorldState) -> dict[str, Any]:
        return {
            "world_id": state.world_id,
            "marker_id": state.marker_id,
            "applied_marker_count": state.applied_marker_count,
            "entities": [entity.model_dump(mode="json") for entity in state.entities],
            "relations": [relation.model_dump(mode="json") for relation in state.relations],
        }

    def _state_hash(self, state_json: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(state_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _world_state_from_snapshot(
        self,
        world_id: str,
        marker_id: str,
        snapshot: TimelineSnapshot,
    ) -> TimelineWorldState:
        state_json = snapshot.state_json or {}
        entities_raw = state_json.get("entities")
        relations_raw = state_json.get("relations")
        if not isinstance(entities_raw, list) or not isinstance(relations_raw, list):
            raise ValueError("Invalid timeline snapshot shape")

        entities = [Entity(**entity) for entity in entities_raw]
        entities.sort(key=lambda entity: entity.name.lower())

        entity_by_id = {entity.id: entity for entity in entities}
        entity_ids = set(entity_by_id.keys())
        relations = [
            Relation(**relation)
            for relation in relations_raw
            if relation.get("source_entity_id") in entity_ids
            and relation.get("target_entity_id") in entity_ids
        ]
        for relation in relations:
            source_entity = entity_by_id.get(relation.source_entity_id)
            target_entity = entity_by_id.get(relation.target_entity_id)
            source_exists = source_entity.exists_at_marker if source_entity else False
            target_exists = target_entity.exists_at_marker if target_entity else False
            relation.exists_at_marker = bool(relation.exists_at_marker and source_exists and target_exists)
        relations.sort(key=lambda relation: (relation.created_at, relation.id))

        applied_marker_count = int(
            state_json.get("applied_marker_count", snapshot.applied_marker_count),
        )
        return TimelineWorldState(
            world_id=world_id,
            marker_id=marker_id,
            applied_marker_count=applied_marker_count,
            entities=entities,
            relations=relations,
            from_snapshot_marker_id=marker_id,
            note="Loaded from cached timeline snapshot.",
        )

    async def generate_snapshot(self, world_id: str, marker_id: str) -> TimelineSnapshot:
        state = await self.get_world_state(world_id, marker_id, use_snapshot=False)
        state_json = self._state_json_from_world_state(state)
        state_hash = self._state_hash(state_json)
        return await self.upsert_snapshot(
            world_id=world_id,
            marker_id=marker_id,
            data=TimelineSnapshotUpsert(
                state_json=state_json,
                state_hash=state_hash,
                applied_marker_count=state.applied_marker_count,
                entity_count=len(state.entities),
                relation_count=len(state.relations),
            ),
        )

    async def rebuild_snapshots(self, world_id: str) -> TimelineRebuildResult:
        markers = await self.list_markers(world_id, include_operations=False)

        db = await self._get_db()
        try:
            await db.execute(
                "DELETE FROM timeline_snapshots WHERE world_id = ?",
                (world_id,),
            )
            await db.commit()
        finally:
            await db.close()

        for marker in markers:
            await self.generate_snapshot(world_id, marker.id)

        return TimelineRebuildResult(
            world_id=world_id,
            marker_count=len(markers),
            snapshot_count=len(markers),
            rebuilt_at=datetime.now(timezone.utc),
        )

    async def _list_base_entities(self, world_id: str) -> list[dict[str, Any]]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM entities WHERE world_id = ? ORDER BY name ASC",
                (world_id,),
            )
            rows = await cursor.fetchall()
            return [dict(_row_to_entity(dict(row)).model_dump()) for row in rows]
        finally:
            await db.close()

    async def _list_base_relations(self, world_id: str) -> list[dict[str, Any]]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM relations WHERE world_id = ? ORDER BY created_at ASC",
                (world_id,),
            )
            rows = await cursor.fetchall()
            return [dict(_row_to_relation(dict(row)).model_dump()) for row in rows]
        finally:
            await db.close()

    async def _list_operations_up_to(
        self,
        world_id: str,
        marker_sort_key: float | None,
    ) -> list[TimelineOperation]:
        db = await self._get_db()
        try:
            if marker_sort_key is None:
                cursor = await db.execute(
                    """SELECT o.* FROM timeline_operations o
                       JOIN timeline_markers m ON m.id = o.marker_id
                       WHERE o.world_id = ?
                       ORDER BY m.sort_key ASC, m.created_at ASC, m.id ASC, o.order_index ASC, o.created_at ASC, o.id ASC""",
                    (world_id,),
                )
            else:
                cursor = await db.execute(
                    """SELECT o.* FROM timeline_operations o
                       JOIN timeline_markers m ON m.id = o.marker_id
                       WHERE o.world_id = ? AND m.sort_key <= ?
                       ORDER BY m.sort_key ASC, m.created_at ASC, m.id ASC, o.order_index ASC, o.created_at ASC, o.id ASC""",
                    (world_id, marker_sort_key),
                )
            rows = await cursor.fetchall()
            return [_row_to_operation(dict(row)) for row in rows]
        finally:
            await db.close()

    async def _creation_sort_keys(
        self,
        world_id: str,
    ) -> tuple[dict[str, float], dict[str, float]]:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                """SELECT o.target_kind, o.target_id, o.op_type, m.sort_key
                   FROM timeline_operations o
                   JOIN timeline_markers m ON m.id = o.marker_id
                   WHERE o.world_id = ? AND o.target_id IS NOT NULL
                   ORDER BY m.sort_key ASC, m.created_at ASC, m.id ASC, o.order_index ASC, o.created_at ASC, o.id ASC""",
                (world_id,),
            )
            rows = await cursor.fetchall()
        finally:
            await db.close()

        entity_create_ops = {"entity_create", "entity_add"}
        relation_create_ops = {"relation_create", "relation_add"}
        entity_first_created_at: dict[str, float] = {}
        relation_first_created_at: dict[str, float] = {}

        for row in rows:
            target_id = row["target_id"]
            if not target_id:
                continue
            op_type = normalize_type(row["op_type"])
            target_kind = normalize_type(row["target_kind"])
            sort_key = float(row["sort_key"])

            if target_kind == "entity" and op_type in entity_create_ops:
                entity_first_created_at.setdefault(target_id, sort_key)
            if target_kind == "relation" and op_type in relation_create_ops:
                relation_first_created_at.setdefault(target_id, sort_key)

        return entity_first_created_at, relation_first_created_at

    async def _count_markers_up_to(self, world_id: str, marker_sort_key: float | None) -> int:
        db = await self._get_db()
        try:
            if marker_sort_key is None:
                cursor = await db.execute(
                    "SELECT COUNT(*) AS marker_count FROM timeline_markers WHERE world_id = ?",
                    (world_id,),
                )
            else:
                cursor = await db.execute(
                    "SELECT COUNT(*) AS marker_count FROM timeline_markers WHERE world_id = ? AND sort_key <= ?",
                    (world_id, marker_sort_key),
                )
            row = await cursor.fetchone()
            if not row:
                return 0
            return int(row["marker_count"])
        finally:
            await db.close()

    async def _nearest_snapshot_marker(
        self,
        world_id: str,
        marker_sort_key: float | None,
    ) -> str | None:
        db = await self._get_db()
        try:
            if marker_sort_key is None:
                cursor = await db.execute(
                    """SELECT s.marker_id
                       FROM timeline_snapshots s
                       JOIN timeline_markers m ON m.id = s.marker_id
                       WHERE s.world_id = ?
                       ORDER BY m.sort_key DESC, s.updated_at DESC
                       LIMIT 1""",
                    (world_id,),
                )
            else:
                cursor = await db.execute(
                    """SELECT s.marker_id
                       FROM timeline_snapshots s
                       JOIN timeline_markers m ON m.id = s.marker_id
                       WHERE s.world_id = ? AND m.sort_key <= ?
                       ORDER BY m.sort_key DESC, s.updated_at DESC
                       LIMIT 1""",
                    (world_id, marker_sort_key),
                )
            row = await cursor.fetchone()
            if not row:
                return None
            return row["marker_id"]
        finally:
            await db.close()

    def _apply_operations(
        self,
        world_id: str,
        entity_map: dict[str, dict[str, Any]],
        relation_map: dict[str, dict[str, Any]],
        entity_exists_map: dict[str, bool],
        relation_exists_map: dict[str, bool],
        operations: list[TimelineOperation],
    ) -> None:
        entity_create_ops = {"entity_create", "entity_add"}
        entity_update_ops = {"entity_update", "entity_patch", "entity_modify"}
        entity_delete_ops = {"entity_delete", "entity_remove"}
        relation_create_ops = {"relation_create", "relation_add"}
        relation_update_ops = {"relation_update", "relation_patch", "relation_modify"}
        relation_delete_ops = {"relation_delete", "relation_remove"}

        def _ensure_entity(target_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
            current = entity_map.get(target_id)
            if current:
                return current

            name = payload.get("name")
            if not name:
                return None
            entity_type = (
                payload.get("type")
                or payload.get("entity_type")
                or payload.get("kind")
                or "concept"
            )
            now = _now()
            current = {
                "id": target_id,
                "world_id": world_id,
                "name": name,
                "type": normalize_type(entity_type),
                "subtype": normalize_type(payload["subtype"]) if payload.get("subtype") else None,
                "aliases": payload.get("aliases", []),
                "context": payload.get("context"),
                "summary": payload.get("summary"),
                "tags": payload.get("tags", []),
                "image_url": payload.get("image_url"),
                "status": payload.get("status", "active"),
                "exists_at_marker": True,
                "source": payload.get("source", "user"),
                "source_note_id": payload.get("source_note_id"),
                "created_at": payload.get("created_at", now),
                "updated_at": payload.get("updated_at", now),
            }
            entity_map[target_id] = current
            return current

        def _patch_entity(current: dict[str, Any], payload: dict[str, Any]) -> None:
            if "name" in payload:
                current["name"] = payload["name"]
            if "type" in payload:
                current["type"] = normalize_type(payload["type"])
            if "subtype" in payload:
                current["subtype"] = (
                    normalize_type(payload["subtype"])
                    if payload.get("subtype")
                    else None
                )
            if "aliases" in payload:
                current["aliases"] = payload["aliases"] or []
            if "context" in payload:
                current["context"] = payload["context"]
            if "summary" in payload:
                current["summary"] = payload["summary"]
            if "tags" in payload:
                current["tags"] = payload["tags"] or []
            if "image_url" in payload:
                current["image_url"] = payload["image_url"]
            if "status" in payload and payload.get("status") is not None:
                current["status"] = str(payload["status"])
            current["updated_at"] = _now()

        for operation in operations:
            op_type = normalize_type(operation.op_type)
            target_kind = normalize_type(operation.target_kind)
            payload = operation.payload if isinstance(operation.payload, dict) else {}

            if target_kind == "entity":
                target_id = operation.target_id or payload.get("id")

                if op_type in entity_create_ops:
                    if not target_id:
                        continue
                    current = _ensure_entity(target_id, payload)
                    if not current:
                        continue
                    _patch_entity(current, payload)
                    entity_exists_map[target_id] = True
                    current["exists_at_marker"] = True
                    continue

                if op_type in entity_update_ops:
                    if not target_id:
                        continue
                    current = _ensure_entity(target_id, payload)
                    if not current:
                        continue
                    _patch_entity(current, payload)
                    if target_id not in entity_exists_map:
                        entity_exists_map[target_id] = True
                    current["exists_at_marker"] = bool(entity_exists_map.get(target_id, True))
                    continue

                if op_type in entity_delete_ops:
                    if not target_id:
                        continue
                    current = entity_map.get(target_id)
                    if current:
                        if "status" in payload and payload.get("status") is not None:
                            current["status"] = str(payload["status"])
                        current["updated_at"] = _now()
                        current["exists_at_marker"] = False
                    entity_exists_map[target_id] = False
                    continue

            if target_kind == "relation":
                target_id = operation.target_id or payload.get("id")

                if op_type in relation_create_ops:
                    if not target_id:
                        continue
                    current = relation_map.get(target_id)
                    if not current:
                        source_entity_id = payload.get("source_entity_id")
                        target_entity_id = payload.get("target_entity_id")
                        relation_type = (
                            payload.get("type")
                            or payload.get("relation_type")
                            or payload.get("kind")
                            or "related_to"
                        )
                        if not source_entity_id or not target_entity_id:
                            continue
                        if source_entity_id not in entity_map or target_entity_id not in entity_map:
                            continue
                        now = _now()
                        current = {
                            "id": target_id,
                            "world_id": world_id,
                            "source_entity_id": source_entity_id,
                            "target_entity_id": target_entity_id,
                            "type": normalize_type(relation_type),
                            "context": payload.get("context"),
                            "weight": payload.get("weight", 0.5),
                            "exists_at_marker": True,
                            "source": payload.get("source", "user"),
                            "source_note_id": payload.get("source_note_id"),
                            "created_at": payload.get("created_at", now),
                            "updated_at": payload.get("updated_at", now),
                        }
                        relation_map[target_id] = current
                    if "source_entity_id" in payload and payload["source_entity_id"] in entity_map:
                        current["source_entity_id"] = payload["source_entity_id"]
                    if "target_entity_id" in payload and payload["target_entity_id"] in entity_map:
                        current["target_entity_id"] = payload["target_entity_id"]
                    if "type" in payload:
                        current["type"] = normalize_type(payload["type"])
                    if "context" in payload:
                        current["context"] = payload["context"]
                    if "weight" in payload:
                        current["weight"] = payload["weight"]
                    current["updated_at"] = _now()
                    current["exists_at_marker"] = True
                    relation_exists_map[target_id] = True
                    continue

                if op_type in relation_update_ops:
                    if not target_id or target_id not in relation_map:
                        continue
                    current = relation_map[target_id]
                    if "source_entity_id" in payload and payload["source_entity_id"] in entity_map:
                        current["source_entity_id"] = payload["source_entity_id"]
                    if "target_entity_id" in payload and payload["target_entity_id"] in entity_map:
                        current["target_entity_id"] = payload["target_entity_id"]
                    if "type" in payload:
                        current["type"] = normalize_type(payload["type"])
                    if "context" in payload:
                        current["context"] = payload["context"]
                    if "weight" in payload:
                        current["weight"] = payload["weight"]
                    current["updated_at"] = _now()
                    if target_id not in relation_exists_map:
                        relation_exists_map[target_id] = True
                    current["exists_at_marker"] = bool(relation_exists_map.get(target_id, True))
                    continue

                if op_type in relation_delete_ops:
                    if not target_id:
                        continue
                    current = relation_map.get(target_id)
                    if current:
                        current["updated_at"] = _now()
                        current["exists_at_marker"] = False
                    relation_exists_map[target_id] = False

    async def get_world_state(
        self,
        world_id: str,
        marker_id: Optional[str] = None,
        use_snapshot: bool = True,
    ) -> TimelineWorldState:
        db = await self._get_db()
        try:
            marker_sort_key = None
            if marker_id:
                marker_sort_key = await self._marker_sort_key(db, world_id, marker_id)
                if marker_sort_key is None:
                    raise ValueError(f"Marker {marker_id} not found in world {world_id}")
        finally:
            await db.close()

        if marker_id and use_snapshot:
            snapshot = await self.get_snapshot(world_id, marker_id)
            if snapshot:
                try:
                    return self._world_state_from_snapshot(world_id, marker_id, snapshot)
                except Exception:
                    pass

        base_entities = await self._list_base_entities(world_id)
        base_relations = await self._list_base_relations(world_id)
        operations = await self._list_operations_up_to(world_id, marker_sort_key)

        entity_map = {
            entity["id"]: {**dict(entity), "exists_at_marker": True}
            for entity in base_entities
        }
        relation_map = {
            relation["id"]: {**dict(relation), "exists_at_marker": True}
            for relation in base_relations
        }
        entity_exists_map: dict[str, bool] = {entity_id: True for entity_id in entity_map}
        relation_exists_map: dict[str, bool] = {relation_id: True for relation_id in relation_map}

        # Treat future-created objects as non-existent before replay so scrubbing
        # can show them greyed out until their creation marker is applied.
        if marker_sort_key is not None:
            entity_created_at, relation_created_at = await self._creation_sort_keys(world_id)
            for entity_id, created_sort_key in entity_created_at.items():
                if created_sort_key > marker_sort_key:
                    entity_exists_map[entity_id] = False
            for relation_id, created_sort_key in relation_created_at.items():
                if created_sort_key > marker_sort_key:
                    relation_exists_map[relation_id] = False

        self._apply_operations(
            world_id,
            entity_map,
            relation_map,
            entity_exists_map,
            relation_exists_map,
            operations,
        )

        entities = []
        for entity in entity_map.values():
            entity_copy = dict(entity)
            entity_copy["exists_at_marker"] = bool(entity_exists_map.get(entity_copy["id"], True))
            entities.append(Entity(**entity_copy))
        entities.sort(key=lambda entity: entity.name.lower())
        entity_exists_by_id = {entity.id: entity.exists_at_marker for entity in entities}

        relations = []
        for relation in relation_map.values():
            source_id = relation["source_entity_id"]
            target_id = relation["target_entity_id"]
            if source_id not in entity_map or target_id not in entity_map:
                continue
            relation_copy = dict(relation)
            relation_exists = bool(relation_exists_map.get(relation_copy["id"], True))
            relation_copy["exists_at_marker"] = (
                relation_exists
                and bool(entity_exists_by_id.get(source_id, False))
                and bool(entity_exists_by_id.get(target_id, False))
            )
            relations.append(Relation(**relation_copy))
        relations.sort(key=lambda relation: (relation.created_at, relation.id))

        applied_marker_count = await self._count_markers_up_to(world_id, marker_sort_key)
        from_snapshot_marker_id = await self._nearest_snapshot_marker(world_id, marker_sort_key)

        return TimelineWorldState(
            world_id=world_id,
            marker_id=marker_id,
            applied_marker_count=applied_marker_count,
            entities=entities,
            relations=relations,
            from_snapshot_marker_id=from_snapshot_marker_id,
            note=(
                "Baseline entities/relations come from canonical tables, "
                "then timeline operations are replayed in marker order."
            ),
        )
