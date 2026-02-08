"""Canon Guardian service with deterministic hard-rule contradiction checks."""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from app.logging import get_logger
from app.models import (
    GuardianAction,
    GuardianApplyRequest,
    GuardianApplyResult,
    GuardianEvidenceRef,
    GuardianFinding,
    GuardianFindingStatusUpdate,
    GuardianRun,
    GuardianRunDetail,
    GuardianScanAccepted,
    GuardianScanRequest,
    normalize_type,
)
from app.services.backboard import BackboardService
from app.services.prompts import build_canon_guardian_soft_critic_prompt

logger = get_logger("services.canon_guardian")

INACTIVE_ENTITY_STATUSES = {"inactive", "deceased", "dead", "destroyed", "retired", "gone"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
ENTITY_OPS = {"entity_create", "entity_patch", "entity_delete", "entity_add", "entity_update", "entity_modify", "entity_remove"}
RELATION_OPS = {"relation_create", "relation_patch", "relation_delete", "relation_add", "relation_update", "relation_modify", "relation_remove"}
WORLD_OPS = {"world_patch"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}
ALLOWED_ACTION_TYPES = {"timeline_operation", "entity_patch", "relation_patch", "world_patch", "noop"}
ALLOWED_EVIDENCE_KINDS = {"note", "entity", "relation", "timeline_marker", "timeline_operation", "world"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _normalize_identity(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _phrase_in_text(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_identity(phrase)
    if not normalized_phrase or len(normalized_phrase) < 2:
        return False
    escaped = re.escape(normalized_phrase)
    if re.search(rf"(?<!\w){escaped}(?!\w)", text):
        return True
    return normalized_phrase in text


def _row_to_run(row: dict) -> GuardianRun:
    return GuardianRun(
        id=row["id"],
        world_id=row["world_id"],
        trigger_kind=row["trigger_kind"],
        status=row["status"],
        request=_load_json(row.get("request_json"), {}),
        summary=_load_json(row.get("summary_json"), None),
        error=row.get("error"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_finding(row: dict) -> GuardianFinding:
    evidence_rows = _load_json(row.get("evidence_json"), [])
    evidence = [GuardianEvidenceRef(**entry) for entry in evidence_rows]
    return GuardianFinding(
        id=row["id"],
        run_id=row["run_id"],
        world_id=row["world_id"],
        severity=row["severity"],
        finding_code=row["finding_code"],
        title=row["title"],
        detail=row["detail"],
        confidence=row["confidence"],
        resolution_status=row["resolution_status"],
        evidence=evidence,
        suggested_action_count=row["suggested_action_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_action(row: dict) -> GuardianAction:
    return GuardianAction(
        id=row["id"],
        run_id=row["run_id"],
        finding_id=row.get("finding_id"),
        world_id=row["world_id"],
        action_type=row["action_type"],
        op_type=row.get("op_type"),
        target_kind=row.get("target_kind"),
        target_id=row.get("target_id"),
        payload=_load_json(row.get("payload"), {}),
        rationale=row.get("rationale"),
        status=row["status"],
        error=row.get("error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class CanonGuardianService:
    """Canonical contradiction scanning service (hard rules + optional soft critic)."""

    def __init__(self, db_path: str, backboard: BackboardService | None = None):
        self.db_path = db_path
        self.backboard = backboard

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _world_exists(self, db: aiosqlite.Connection, world_id: str) -> bool:
        cursor = await db.execute("SELECT 1 FROM worlds WHERE id = ?", (world_id,))
        row = await cursor.fetchone()
        return row is not None

    async def _get_world_assistant_id(self, db: aiosqlite.Connection, world_id: str) -> str | None:
        cursor = await db.execute("SELECT assistant_id FROM worlds WHERE id = ?", (world_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        assistant_id = row["assistant_id"]
        return str(assistant_id) if assistant_id else None

    async def _list_notes(self, db: aiosqlite.Connection, world_id: str) -> list[dict]:
        cursor = await db.execute(
            """SELECT id, world_id, title, content, analysis_thread_id, created_at, updated_at
               FROM notes
               WHERE world_id = ?
               ORDER BY updated_at DESC, created_at DESC, id DESC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _list_entities(self, db: aiosqlite.Connection, world_id: str) -> list[dict]:
        cursor = await db.execute(
            """SELECT id, world_id, name, type, aliases, status, source_note_id, created_at, updated_at
               FROM entities
               WHERE world_id = ?
               ORDER BY name ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        entities: list[dict] = []
        for row in rows:
            entity = dict(row)
            entity["aliases"] = _load_json(entity.get("aliases"), [])
            entity["status"] = str(entity.get("status") or "active")
            entities.append(entity)
        return entities

    async def _list_relations(self, db: aiosqlite.Connection, world_id: str) -> list[dict]:
        cursor = await db.execute(
            """SELECT id, world_id, source_entity_id, target_entity_id, type, context, weight, source_note_id, created_at, updated_at
               FROM relations
               WHERE world_id = ?
               ORDER BY created_at ASC, id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _list_markers(self, db: aiosqlite.Connection, world_id: str) -> list[dict]:
        cursor = await db.execute(
            """SELECT id, world_id, title, marker_kind, date_label, date_sort_value, sort_key, source_note_id, created_at, updated_at
               FROM timeline_markers
               WHERE world_id = ?
               ORDER BY sort_key ASC, created_at ASC, id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _list_operations(self, db: aiosqlite.Connection, world_id: str) -> list[dict]:
        cursor = await db.execute(
            """SELECT
                   o.id,
                   o.world_id,
                   o.marker_id,
                   o.op_type,
                   o.target_kind,
                   o.target_id,
                   o.payload,
                   o.order_index,
                   o.created_at,
                   o.updated_at,
                   m.sort_key AS marker_sort_key,
                   m.marker_kind AS marker_kind,
                   m.date_sort_value AS marker_date_sort_value
               FROM timeline_operations o
               JOIN timeline_markers m ON m.id = o.marker_id
               WHERE o.world_id = ?
               ORDER BY m.sort_key ASC, m.created_at ASC, m.id ASC, o.order_index ASC, o.created_at ASC, o.id ASC""",
            (world_id,),
        )
        rows = await cursor.fetchall()
        operations: list[dict] = []
        for row in rows:
            operation = dict(row)
            operation["payload"] = _load_json(operation.get("payload"), {})
            operation["op_type"] = normalize_type(operation.get("op_type") or "")
            operation["target_kind"] = normalize_type(operation.get("target_kind") or "")
            operations.append(operation)
        return operations

    def _extract_scope_entity_ids(
        self,
        note_title: str | None,
        note_content: str | None,
        entities: list[dict],
    ) -> set[str]:
        text = _normalize_identity(f"{note_title or ''}\n{note_content or ''}")
        if not text:
            return set()
        scope: set[str] = set()
        for entity in entities:
            candidates = [entity.get("name") or ""]
            candidates.extend(entity.get("aliases") or [])
            candidates = sorted({candidate for candidate in candidates if candidate}, key=len, reverse=True)
            for candidate in candidates:
                if _phrase_in_text(text, candidate):
                    scope.add(entity["id"])
                    break
        return scope

    def _new_finding(
        self,
        run_id: str,
        world_id: str,
        severity: str,
        code: str,
        title: str,
        detail: str,
        confidence: float,
        evidence: list[dict[str, str]],
    ) -> GuardianFinding:
        return GuardianFinding(
            id=str(uuid4()),
            run_id=run_id,
            world_id=world_id,
            severity=severity,
            finding_code=code,
            title=title,
            detail=detail,
            confidence=confidence,
            resolution_status="open",
            evidence=[GuardianEvidenceRef(**entry) for entry in evidence],
            suggested_action_count=0,
            created_at=_now(),
            updated_at=_now(),
        )

    def _new_action(
        self,
        run_id: str,
        world_id: str,
        finding_id: str | None,
        action_type: str,
        rationale: str,
        *,
        op_type: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> GuardianAction:
        return GuardianAction(
            id=str(uuid4()),
            run_id=run_id,
            finding_id=finding_id,
            world_id=world_id,
            action_type=action_type,  # type: ignore[arg-type]
            op_type=op_type,
            target_kind=target_kind,
            target_id=target_id,
            payload=payload or {},
            rationale=rationale,
            status="proposed",
            created_at=_now(),
            updated_at=_now(),
        )

    def _is_in_scope(self, scope_entity_ids: set[str], *entity_ids: str | None) -> bool:
        if not scope_entity_ids:
            return True
        for entity_id in entity_ids:
            if entity_id and entity_id in scope_entity_ids:
                return True
        return False

    def _run_hard_rules(
        self,
        *,
        run_id: str,
        world_id: str,
        note_title: str | None,
        note_content: str | None,
        entities: list[dict],
        relations: list[dict],
        markers: list[dict],
        operations: list[dict],
    ) -> tuple[list[GuardianFinding], list[GuardianAction], dict[str, Any]]:
        logger.info(
            "[TEMP][CANON][hard] start run_id=%s world_id=%s entities=%d relations=%d markers=%d operations=%d",
            run_id,
            world_id,
            len(entities),
            len(relations),
            len(markers),
            len(operations),
        )
        findings: list[GuardianFinding] = []
        actions: list[GuardianAction] = []

        entity_by_id = {entity["id"]: entity for entity in entities}
        relation_by_id = {relation["id"]: relation for relation in relations}
        scope_entity_ids = self._extract_scope_entity_ids(note_title, note_content, entities)

        identity_map: dict[str, set[str]] = defaultdict(set)
        for entity in entities:
            identity_map[_normalize_identity(entity.get("name"))].add(entity["id"])
            for alias in entity.get("aliases") or []:
                alias_key = _normalize_identity(alias)
                if alias_key:
                    identity_map[alias_key].add(entity["id"])

        for identity, entity_ids in identity_map.items():
            normalized_ids = sorted(entity_ids)
            if not identity or len(normalized_ids) < 2:
                continue
            if scope_entity_ids and not set(normalized_ids).intersection(scope_entity_ids):
                continue
            snippet = ", ".join(entity_by_id[eid]["name"] for eid in normalized_ids[:4])
            finding = self._new_finding(
                run_id=run_id,
                world_id=world_id,
                severity="high",
                code="duplicate_entity_identity",
                title=f"Multiple entities share identity key '{identity}'",
                detail=f"Identity '{identity}' maps to {len(normalized_ids)} entities ({snippet}).",
                confidence=1.0,
                evidence=[{"kind": "entity", "id": eid} for eid in normalized_ids[:8]],
            )
            findings.append(finding)
            actions.append(
                self._new_action(
                    run_id=run_id,
                    world_id=world_id,
                    finding_id=finding.id,
                    action_type="noop",
                    rationale="Manual merge/disambiguation recommended for duplicate identity keys.",
                )
            )

        for relation in relations:
            source = entity_by_id.get(relation["source_entity_id"])
            target = entity_by_id.get(relation["target_entity_id"])
            if not source or not target:
                continue
            if not self._is_in_scope(scope_entity_ids, source["id"], target["id"]):
                continue
            source_status = _normalize_identity(source.get("status"))
            target_status = _normalize_identity(target.get("status"))
            if source_status not in INACTIVE_ENTITY_STATUSES and target_status not in INACTIVE_ENTITY_STATUSES:
                continue
            finding = self._new_finding(
                run_id=run_id,
                world_id=world_id,
                severity="high",
                code="inactive_entity_in_relation",
                title="Inactive/deceased entity participates in an active relation",
                detail=(
                    f"Relation '{relation['type']}' links '{source['name']}' ({source['status']}) "
                    f"to '{target['name']}' ({target['status']})."
                ),
                confidence=1.0,
                evidence=[
                    {"kind": "relation", "id": relation["id"]},
                    {"kind": "entity", "id": source["id"]},
                    {"kind": "entity", "id": target["id"]},
                ],
            )
            findings.append(finding)
            actions.append(
                self._new_action(
                    run_id=run_id,
                    world_id=world_id,
                    finding_id=finding.id,
                    action_type="relation_patch",
                    target_kind="relation",
                    target_id=relation["id"],
                    payload={"review": "Confirm historical vs active relation semantics."},
                    rationale="Mark relation as historical or adjust entity status.",
                )
            )

        # 3) Conflicting or duplicate relation semantics.
        relation_triplets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        relation_pairs: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for relation in relations:
            relation_type = normalize_type(relation.get("type") or "")
            triplet_key = (
                relation["source_entity_id"],
                relation["target_entity_id"],
                relation_type,
            )
            relation_triplets[triplet_key].append(relation)
            relation_pairs[(relation["source_entity_id"], relation["target_entity_id"])][relation_type].append(relation)

        for (source_id, target_id, relation_type), rows in relation_triplets.items():
            if len(rows) <= 1:
                continue
            if not self._is_in_scope(scope_entity_ids, source_id, target_id):
                continue
            source_name = entity_by_id.get(source_id, {}).get("name", source_id)
            target_name = entity_by_id.get(target_id, {}).get("name", target_id)
            finding = self._new_finding(
                run_id=run_id,
                world_id=world_id,
                severity="medium",
                code="duplicate_relation_edge",
                title="Duplicate relation edges detected",
                detail=f"Found {len(rows)} duplicate '{relation_type}' relations from '{source_name}' to '{target_name}'.",
                confidence=1.0,
                evidence=[{"kind": "relation", "id": row["id"]} for row in rows[:8]],
            )
            findings.append(finding)
            actions.append(
                self._new_action(
                    run_id=run_id,
                    world_id=world_id,
                    finding_id=finding.id,
                    action_type="relation_patch",
                    target_kind="relation",
                    target_id=rows[0]["id"],
                    payload={"dedupe_candidate_relation_ids": [row["id"] for row in rows[1:]]},
                    rationale="Review and remove duplicate edges.",
                )
            )

        contradictory_pairs = [("ally_of", "enemy_of"), ("parent_of", "child_of")]
        for (source_id, target_id), by_type in relation_pairs.items():
            if not self._is_in_scope(scope_entity_ids, source_id, target_id):
                continue
            for left, right in contradictory_pairs:
                if left not in by_type or right not in by_type:
                    continue
                left_rel = by_type[left][0]
                right_rel = by_type[right][0]
                source_name = entity_by_id.get(source_id, {}).get("name", source_id)
                target_name = entity_by_id.get(target_id, {}).get("name", target_id)
                finding = self._new_finding(
                    run_id=run_id,
                    world_id=world_id,
                    severity="high",
                    code="conflicting_relation_types",
                    title="Conflicting relation types on same directed pair",
                    detail=f"'{source_name}' -> '{target_name}' has both '{left}' and '{right}'.",
                    confidence=1.0,
                    evidence=[
                        {"kind": "relation", "id": left_rel["id"]},
                        {"kind": "relation", "id": right_rel["id"]},
                    ],
                )
                findings.append(finding)
                actions.append(
                    self._new_action(
                        run_id=run_id,
                        world_id=world_id,
                        finding_id=finding.id,
                        action_type="noop",
                        rationale="Resolve contradictory relation semantics manually.",
                    )
                )

        parent_edges = {(src, tgt) for (src, tgt), types in relation_pairs.items() if "parent_of" in types}
        for source_id, target_id in sorted(parent_edges):
            if (target_id, source_id) not in parent_edges:
                continue
            if source_id > target_id:
                continue
            if not self._is_in_scope(scope_entity_ids, source_id, target_id):
                continue
            source_name = entity_by_id.get(source_id, {}).get("name", source_id)
            target_name = entity_by_id.get(target_id, {}).get("name", target_id)
            forward_id = relation_pairs[(source_id, target_id)]["parent_of"][0]["id"]
            reverse_id = relation_pairs[(target_id, source_id)]["parent_of"][0]["id"]
            finding = self._new_finding(
                run_id=run_id,
                world_id=world_id,
                severity="critical",
                code="cyclic_parent_relation",
                title="Cyclic parent_of relationship detected",
                detail=f"Both '{source_name} parent_of {target_name}' and reverse parent_of relation exist.",
                confidence=1.0,
                evidence=[
                    {"kind": "relation", "id": forward_id},
                    {"kind": "relation", "id": reverse_id},
                ],
            )
            findings.append(finding)
            actions.append(
                self._new_action(
                    run_id=run_id,
                    world_id=world_id,
                    finding_id=finding.id,
                    action_type="noop",
                    rationale="Keep only one parent_of direction and convert inverse to child_of if needed.",
                )
            )

        # 4) Type/schema validations on canonical tables.
        for entity in entities:
            normalized_type = normalize_type(entity.get("type") or "")
            raw_type = entity.get("type") or ""
            if raw_type != normalized_type:
                if not self._is_in_scope(scope_entity_ids, entity["id"]):
                    continue
                finding = self._new_finding(
                    run_id=run_id,
                    world_id=world_id,
                    severity="low",
                    code="unnormalized_entity_type",
                    title="Entity type is not normalized",
                    detail=f"Entity '{entity['name']}' has type '{raw_type}', expected '{normalized_type}'.",
                    confidence=1.0,
                    evidence=[{"kind": "entity", "id": entity["id"]}],
                )
                findings.append(finding)
                actions.append(
                    self._new_action(
                        run_id=run_id,
                        world_id=world_id,
                        finding_id=finding.id,
                        action_type="entity_patch",
                        target_kind="entity",
                        target_id=entity["id"],
                        payload={"type": normalized_type},
                        rationale="Normalize entity type casing/spacing.",
                    )
                )

        for relation in relations:
            normalized_relation_type = normalize_type(relation.get("type") or "")
            raw_relation_type = relation.get("type") or ""
            if raw_relation_type != normalized_relation_type:
                source_id = relation.get("source_entity_id")
                target_id = relation.get("target_entity_id")
                if not self._is_in_scope(scope_entity_ids, source_id, target_id):
                    continue
                finding = self._new_finding(
                    run_id=run_id,
                    world_id=world_id,
                    severity="low",
                    code="unnormalized_relation_type",
                    title="Relation type is not normalized",
                    detail=f"Relation '{relation['id']}' has type '{raw_relation_type}', expected '{normalized_relation_type}'.",
                    confidence=1.0,
                    evidence=[{"kind": "relation", "id": relation["id"]}],
                )
                findings.append(finding)
                actions.append(
                    self._new_action(
                        run_id=run_id,
                        world_id=world_id,
                        finding_id=finding.id,
                        action_type="relation_patch",
                        target_kind="relation",
                        target_id=relation["id"],
                        payload={"type": normalized_relation_type},
                        rationale="Normalize relation type casing/spacing.",
                    )
                )

            weight = relation.get("weight")
            if isinstance(weight, (int, float)) and not (0.0 <= float(weight) <= 1.0):
                source_id = relation.get("source_entity_id")
                target_id = relation.get("target_entity_id")
                if not self._is_in_scope(scope_entity_ids, source_id, target_id):
                    continue
                finding = self._new_finding(
                    run_id=run_id,
                    world_id=world_id,
                    severity="high",
                    code="relation_weight_out_of_range",
                    title="Relation weight out of range",
                    detail=f"Relation '{relation['id']}' has weight {weight}; expected 0.0..1.0.",
                    confidence=1.0,
                    evidence=[{"kind": "relation", "id": relation["id"]}],
                )
                findings.append(finding)
                actions.append(
                    self._new_action(
                        run_id=run_id,
                        world_id=world_id,
                        finding_id=finding.id,
                        action_type="relation_patch",
                        target_kind="relation",
                        target_id=relation["id"],
                        payload={"weight": max(0.0, min(1.0, float(weight)))},
                        rationale="Clamp relation weight to valid range.",
                    )
                )

        # 5) Timeline ordering and operation schema conflicts.
        explicit_markers = [marker for marker in markers if normalize_type(marker.get("marker_kind") or "") == "explicit"]
        previous_explicit_with_date: dict | None = None
        for marker in explicit_markers:
            marker_id = marker["id"]
            has_date = marker.get("date_sort_value") is not None
            if not has_date:
                finding = self._new_finding(
                    run_id=run_id,
                    world_id=world_id,
                    severity="medium",
                    code="explicit_marker_missing_date_sort",
                    title="Explicit marker missing date_sort_value",
                    detail=f"Marker '{marker.get('title') or marker_id}' is explicit but has no numeric date_sort_value.",
                    confidence=1.0,
                    evidence=[{"kind": "timeline_marker", "id": marker_id}],
                )
                findings.append(finding)
                actions.append(
                    self._new_action(
                        run_id=run_id,
                        world_id=world_id,
                        finding_id=finding.id,
                        action_type="noop",
                        rationale="Provide numeric date_sort_value for explicit chronology.",
                    )
                )
                continue

            if previous_explicit_with_date is not None:
                prev_value = float(previous_explicit_with_date["date_sort_value"])
                current_value = float(marker["date_sort_value"])
                if current_value < prev_value:
                    finding = self._new_finding(
                        run_id=run_id,
                        world_id=world_id,
                        severity="high",
                        code="timeline_explicit_order_conflict",
                        title="Explicit timeline order conflicts with date_sort_value",
                        detail=(
                            f"Marker '{marker.get('title')}' ({current_value}) appears after "
                            f"'{previous_explicit_with_date.get('title')}' ({prev_value}) by sort_key."
                        ),
                        confidence=1.0,
                        evidence=[
                            {"kind": "timeline_marker", "id": previous_explicit_with_date["id"]},
                            {"kind": "timeline_marker", "id": marker_id},
                        ],
                    )
                    findings.append(finding)
                    actions.append(
                        self._new_action(
                            run_id=run_id,
                            world_id=world_id,
                            finding_id=finding.id,
                            action_type="noop",
                            rationale="Reposition markers to align sort_key with date_sort_value.",
                        )
                    )
            previous_explicit_with_date = marker

        for operation in operations:
            target_kind = operation.get("target_kind") or ""
            op_type = operation.get("op_type") or ""
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            op_id = operation["id"]
            marker_id = operation["marker_id"]

            if target_kind == "entity" and op_type not in ENTITY_OPS:
                findings.append(
                    self._new_finding(
                        run_id=run_id,
                        world_id=world_id,
                        severity="high",
                        code="invalid_timeline_entity_op_type",
                        title="Invalid entity timeline operation type",
                        detail=f"Operation '{op_id}' has unsupported entity op_type '{op_type}'.",
                        confidence=1.0,
                        evidence=[{"kind": "timeline_operation", "id": op_id}, {"kind": "timeline_marker", "id": marker_id}],
                    )
                )
                continue
            if target_kind == "relation" and op_type not in RELATION_OPS:
                findings.append(
                    self._new_finding(
                        run_id=run_id,
                        world_id=world_id,
                        severity="high",
                        code="invalid_timeline_relation_op_type",
                        title="Invalid relation timeline operation type",
                        detail=f"Operation '{op_id}' has unsupported relation op_type '{op_type}'.",
                        confidence=1.0,
                        evidence=[{"kind": "timeline_operation", "id": op_id}, {"kind": "timeline_marker", "id": marker_id}],
                    )
                )
                continue
            if target_kind == "world" and op_type not in WORLD_OPS:
                findings.append(
                    self._new_finding(
                        run_id=run_id,
                        world_id=world_id,
                        severity="high",
                        code="invalid_timeline_world_op_type",
                        title="Invalid world timeline operation type",
                        detail=f"Operation '{op_id}' has unsupported world op_type '{op_type}'.",
                        confidence=1.0,
                        evidence=[{"kind": "timeline_operation", "id": op_id}, {"kind": "timeline_marker", "id": marker_id}],
                    )
                )
                continue

            target_id = operation.get("target_id")
            if target_kind == "entity":
                if target_id and target_id not in entity_by_id:
                    findings.append(
                        self._new_finding(
                            run_id=run_id,
                            world_id=world_id,
                            severity="high",
                            code="timeline_entity_target_missing",
                            title="Timeline operation references missing entity target",
                            detail=f"Operation '{op_id}' targets unknown entity '{target_id}'.",
                            confidence=1.0,
                            evidence=[{"kind": "timeline_operation", "id": op_id}],
                        )
                    )
                if not target_id and not payload.get("id") and not payload.get("name"):
                    findings.append(
                        self._new_finding(
                            run_id=run_id,
                            world_id=world_id,
                            severity="medium",
                            code="timeline_entity_target_ambiguous",
                            title="Entity timeline operation lacks target reference",
                            detail=f"Operation '{op_id}' has no target_id or payload.name/id to resolve entity.",
                            confidence=1.0,
                            evidence=[{"kind": "timeline_operation", "id": op_id}],
                        )
                    )
            elif target_kind == "relation":
                if target_id and target_id not in relation_by_id:
                    findings.append(
                        self._new_finding(
                            run_id=run_id,
                            world_id=world_id,
                            severity="high",
                            code="timeline_relation_target_missing",
                            title="Timeline operation references missing relation target",
                            detail=f"Operation '{op_id}' targets unknown relation '{target_id}'.",
                            confidence=1.0,
                            evidence=[{"kind": "timeline_operation", "id": op_id}],
                        )
                    )
                if op_type in {"relation_create", "relation_patch", "relation_add", "relation_update", "relation_modify"} and not target_id:
                    missing_fields = [key for key in ("source_entity_id", "target_entity_id", "type") if not payload.get(key)]
                    if missing_fields:
                        findings.append(
                            self._new_finding(
                                run_id=run_id,
                                world_id=world_id,
                                severity="medium",
                                code="timeline_relation_payload_incomplete",
                                title="Relation timeline operation payload is incomplete",
                                detail=f"Operation '{op_id}' without target_id is missing fields: {', '.join(missing_fields)}.",
                                confidence=1.0,
                                evidence=[{"kind": "timeline_operation", "id": op_id}],
                            )
                        )

        summary = {
            "scanner": "hard_rules_v1",
            "scan_scope": "world",
            "scope_entity_count": len(scope_entity_ids),
            "entity_count": len(entities),
            "relation_count": len(relations),
            "marker_count": len(markers),
            "operation_count": len(operations),
            "findings_total": len(findings),
            "actions_total": len(actions),
        }
        logger.info(
            "[TEMP][CANON][hard] complete run_id=%s findings=%d actions=%d scope_entities=%d",
            run_id,
            len(findings),
            len(actions),
            len(scope_entity_ids),
        )
        return findings, actions, summary

    async def _store_findings_and_actions(
        self,
        db: aiosqlite.Connection,
        world_id: str,
        run_id: str,
        findings: list[GuardianFinding],
        actions: list[GuardianAction],
    ) -> None:
        await db.execute("DELETE FROM guardian_actions WHERE world_id = ? AND run_id = ?", (world_id, run_id))
        await db.execute("DELETE FROM guardian_findings WHERE world_id = ? AND run_id = ?", (world_id, run_id))

        action_counts: dict[str, int] = defaultdict(int)
        for action in actions:
            if action.finding_id:
                action_counts[action.finding_id] += 1

        for finding in findings:
            finding.suggested_action_count = action_counts.get(finding.id, 0)
            await db.execute(
                """INSERT INTO guardian_findings
                   (id, run_id, world_id, severity, finding_code, title, detail, confidence, resolution_status, evidence_json, suggested_action_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    finding.id,
                    finding.run_id,
                    finding.world_id,
                    finding.severity,
                    finding.finding_code,
                    finding.title,
                    finding.detail,
                    float(finding.confidence),
                    finding.resolution_status,
                    json.dumps([entry.model_dump() for entry in finding.evidence]),
                    int(finding.suggested_action_count),
                    str(finding.created_at),
                    str(finding.updated_at),
                ),
            )

        for action in actions:
            normalized_target_kind = normalize_type(action.target_kind or "")
            db_target_kind = normalized_target_kind if normalized_target_kind in {"entity", "relation", "world"} else None
            db_target_id = action.target_id if db_target_kind else None
            if action.target_kind and not db_target_kind:
                logger.info(
                    "[TEMP][CANON][scan] action_target_kind_normalized run_id=%s action_id=%s raw_target_kind=%s",
                    run_id,
                    action.id,
                    action.target_kind,
                )
            await db.execute(
                """INSERT INTO guardian_actions
                   (id, run_id, finding_id, world_id, action_type, op_type, target_kind, target_id, payload, rationale, status, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    action.id,
                    action.run_id,
                    action.finding_id,
                    action.world_id,
                    action.action_type,
                    action.op_type,
                    db_target_kind,
                    db_target_id,
                    json.dumps(action.payload),
                    action.rationale,
                    action.status,
                    action.error,
                    str(action.created_at),
                    str(action.updated_at),
                ),
            )

    def _truncate_to_limit(
        self,
        findings: list[GuardianFinding],
        actions: list[GuardianAction],
        max_findings: int,
    ) -> tuple[list[GuardianFinding], list[GuardianAction]]:
        if len(findings) <= max_findings:
            return findings, actions
        ordered_findings = sorted(
            findings,
            key=lambda finding: (SEVERITY_ORDER.get(finding.severity, 99), str(finding.created_at), finding.id),
        )
        selected = ordered_findings[:max_findings]
        selected_ids = {finding.id for finding in selected}
        selected_actions = [action for action in actions if not action.finding_id or action.finding_id in selected_ids]
        return selected, selected_actions

    def _finding_code_family(self, code: str) -> str:
        normalized = normalize_type(code or "")
        return normalized.removeprefix("soft_")

    def _finding_evidence_signature(self, finding: GuardianFinding) -> tuple[str, ...]:
        parts = []
        for item in finding.evidence:
            parts.append(f"{item.kind}:{item.id}")
        return tuple(sorted(parts))

    def _build_soft_critic_context_pack(
        self,
        *,
        note_ids: set[str],
        world_id: str,
        entities: list[dict],
        relations: list[dict],
        markers: list[dict],
        operations: list[dict],
        hard_findings: list[GuardianFinding],
        max_context_tokens: int,
    ) -> tuple[str, dict[str, set[str]], dict[str, Any]]:
        max_chars = max(800, int(max_context_tokens * 4))
        entity_by_id = {entity["id"]: entity for entity in entities}
        relation_by_id = {relation["id"]: relation for relation in relations}
        marker_by_id = {marker["id"]: marker for marker in markers}

        scope_ids = {entity["id"] for entity in entities}

        selected_relations = [
            relation for relation in relations
            if relation["source_entity_id"] in scope_ids or relation["target_entity_id"] in scope_ids
        ]
        neighbor_ids = set(scope_ids)
        for relation in selected_relations:
            neighbor_ids.add(relation["source_entity_id"])
            neighbor_ids.add(relation["target_entity_id"])
        selected_entity_ids = {entity_id for entity_id in neighbor_ids if entity_id in entity_by_id}

        selected_relation_ids = {relation["id"] for relation in selected_relations}
        for relation in relations:
            if relation["source_entity_id"] in selected_entity_ids and relation["target_entity_id"] in selected_entity_ids:
                selected_relation_ids.add(relation["id"])

        selected_operation_ids: set[str] = set()
        selected_marker_ids: set[str] = set()
        for operation in operations:
            target_kind = operation.get("target_kind")
            target_id = operation.get("target_id")
            include = False
            if target_kind == "entity" and target_id in selected_entity_ids:
                include = True
            elif target_kind == "relation" and target_id in selected_relation_ids:
                include = True
            elif operation.get("marker_id") in selected_marker_ids:
                include = True
            if include:
                selected_operation_ids.add(operation["id"])
                selected_marker_ids.add(operation["marker_id"])

        for operation in operations:
            if operation["marker_id"] in selected_marker_ids:
                selected_operation_ids.add(operation["id"])

        selected_entities = [entity_by_id[entity_id] for entity_id in sorted(selected_entity_ids)]
        selected_relations = [relation_by_id[rel_id] for rel_id in sorted(selected_relation_ids) if rel_id in relation_by_id]
        selected_markers = [marker_by_id[marker_id] for marker_id in sorted(selected_marker_ids) if marker_id in marker_by_id]
        selected_operations = [op for op in operations if op["id"] in selected_operation_ids]

        blocks: list[str] = []
        blocks.append(f"[world]\n- world_id: {world_id}\n- scan_scope: world")

        entity_lines = []
        for entity in selected_entities:
            aliases = ", ".join(entity.get("aliases") or [])
            entity_lines.append(
                f"- {entity['id']} | {entity['name']} | type={entity.get('type')} | status={entity.get('status')} | aliases={aliases}"
            )
        blocks.append("[entities]\n" + ("\n".join(entity_lines) if entity_lines else "- none"))

        relation_lines = []
        for relation in selected_relations:
            relation_lines.append(
                f"- {relation['id']} | {relation['source_entity_id']} -> {relation['target_entity_id']} | type={relation.get('type')} | weight={relation.get('weight')}"
            )
        blocks.append("[relations]\n" + ("\n".join(relation_lines) if relation_lines else "- none"))

        marker_lines = []
        for marker in selected_markers:
            marker_lines.append(
                f"- {marker['id']} | {marker.get('title')} | kind={marker.get('marker_kind')} | date_sort_value={marker.get('date_sort_value')} | sort_key={marker.get('sort_key')}"
            )
        blocks.append("[timeline_markers]\n" + ("\n".join(marker_lines) if marker_lines else "- none"))

        operation_lines = []
        for operation in selected_operations:
            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
            payload_keys = ",".join(sorted(payload.keys()))[:120]
            operation_lines.append(
                f"- {operation['id']} | marker={operation['marker_id']} | {operation.get('target_kind')}:{operation.get('target_id')} | op={operation.get('op_type')} | payload_keys={payload_keys}"
            )
        blocks.append("[timeline_operations]\n" + ("\n".join(operation_lines) if operation_lines else "- none"))

        hard_lines = []
        for finding in hard_findings[:20]:
            evidence_sig = ", ".join(f"{e.kind}:{e.id}" for e in finding.evidence[:3])
            hard_lines.append(f"- {finding.finding_code} | severity={finding.severity} | evidence={evidence_sig}")
        blocks.append("[hard_findings_summary]\n" + ("\n".join(hard_lines) if hard_lines else "- none"))

        result_blocks: list[str] = []
        current_chars = 0
        for block in blocks:
            if not block:
                continue
            block_text = block.strip()
            if not block_text:
                continue
            if current_chars + len(block_text) + 2 > max_chars:
                remaining = max_chars - current_chars - 2
                if remaining <= 120:
                    break
                block_text = block_text[:remaining] + "\n...<truncated>"
            result_blocks.append(block_text)
            current_chars += len(block_text) + 2
            if current_chars >= max_chars:
                break

        context_pack = "\n\n".join(result_blocks)
        id_registry = {
            "note": set(note_ids),
            "entity": {entity["id"] for entity in entities},
            "relation": {relation["id"] for relation in relations},
            "timeline_marker": {marker["id"] for marker in markers},
            "timeline_operation": {operation["id"] for operation in operations},
            "world": {world_id},
        }
        meta = {
            "max_context_tokens": max_context_tokens,
            "max_context_chars": max_chars,
            "context_chars": len(context_pack),
            "scope_entity_count": len(scope_ids),
            "selected_entity_count": len(selected_entities),
            "selected_relation_count": len(selected_relations),
            "selected_marker_count": len(selected_markers),
            "selected_operation_count": len(selected_operations),
            "scan_scope": "world",
        }
        return context_pack, id_registry, meta

    def _parse_soft_critic_response(
        self,
        *,
        run_id: str,
        world_id: str,
        raw_response: str,
    ) -> tuple[list[GuardianFinding], list[GuardianAction]]:
        text = (raw_response or "").strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        data = json.loads(text)
        records = data.get("soft_findings", [])
        if not isinstance(records, list):
            return [], []

        findings: list[GuardianFinding] = []
        actions: list[GuardianAction] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            code = normalize_type(str(item.get("finding_code") or "soft_observation"))
            if not code.startswith("soft_"):
                code = f"soft_{code}" if code else "soft_observation"
            severity = normalize_type(str(item.get("severity") or "low"))
            if severity not in ALLOWED_SEVERITIES:
                severity = "low"
            title = str(item.get("title") or "").strip()
            detail = str(item.get("detail") or "").strip()
            if not title or not detail:
                continue
            try:
                confidence = float(item.get("confidence", 0.0))
            except Exception:
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))

            evidence_list: list[dict[str, str]] = []
            for entry in item.get("evidence", []) if isinstance(item.get("evidence"), list) else []:
                if not isinstance(entry, dict):
                    continue
                kind = normalize_type(str(entry.get("kind") or ""))
                evidence_id = str(entry.get("id") or "").strip()
                if kind in ALLOWED_EVIDENCE_KINDS and evidence_id:
                    evidence_entry: dict[str, str] = {"kind": kind, "id": evidence_id}
                    snippet = entry.get("snippet")
                    if snippet is not None:
                        evidence_entry["snippet"] = str(snippet)
                    evidence_list.append(evidence_entry)

            finding = self._new_finding(
                run_id=run_id,
                world_id=world_id,
                severity=severity,
                code=code,
                title=title,
                detail=detail,
                confidence=confidence,
                evidence=evidence_list,
            )
            findings.append(finding)

            suggested_action = item.get("suggested_action")
            if isinstance(suggested_action, dict):
                action_type = normalize_type(str(suggested_action.get("action_type") or "noop"))
                if action_type not in ALLOWED_ACTION_TYPES:
                    action_type = "noop"
                target_kind = suggested_action.get("target_kind")
                if target_kind is not None:
                    target_kind = normalize_type(str(target_kind))
                action = self._new_action(
                    run_id=run_id,
                    world_id=world_id,
                    finding_id=finding.id,
                    action_type=action_type,
                    op_type=normalize_type(str(suggested_action.get("op_type") or "")) or None,
                    target_kind=target_kind or None,
                    target_id=str(suggested_action.get("target_id") or "") or None,
                    payload=suggested_action.get("payload") if isinstance(suggested_action.get("payload"), dict) else {},
                    rationale=str(suggested_action.get("rationale") or "Proposed by soft critic."),
                )
            else:
                action = self._new_action(
                    run_id=run_id,
                    world_id=world_id,
                    finding_id=finding.id,
                    action_type="noop",
                    rationale="No automated remediation suggested.",
                )
            actions.append(action)

        return findings, actions

    def _validate_soft_findings(
        self,
        *,
        soft_findings: list[GuardianFinding],
        soft_actions: list[GuardianAction],
        existing_findings: list[GuardianFinding],
        id_registry: dict[str, set[str]],
        confidence_threshold: float = 0.55,
    ) -> tuple[list[GuardianFinding], list[GuardianAction], dict[str, int]]:
        accepted_findings: list[GuardianFinding] = []
        accepted_actions: list[GuardianAction] = []
        rejected = {
            "low_confidence": 0,
            "invalid_evidence": 0,
            "duplicate": 0,
            "invalid_action_target": 0,
        }
        action_by_finding_id = {action.finding_id: action for action in soft_actions if action.finding_id}

        existing_signatures = {
            (self._finding_code_family(finding.finding_code), self._finding_evidence_signature(finding))
            for finding in existing_findings
        }

        for finding in soft_findings:
            if finding.confidence < confidence_threshold:
                rejected["low_confidence"] += 1
                continue

            if not finding.evidence:
                rejected["invalid_evidence"] += 1
                continue

            evidence_ok = True
            for evidence in finding.evidence:
                valid_ids = id_registry.get(str(evidence.kind), set())
                if evidence.id not in valid_ids:
                    evidence_ok = False
                    break
            if not evidence_ok:
                rejected["invalid_evidence"] += 1
                continue

            signature = (self._finding_code_family(finding.finding_code), self._finding_evidence_signature(finding))
            if signature in existing_signatures:
                rejected["duplicate"] += 1
                continue

            action = action_by_finding_id.get(finding.id)
            if action and action.target_kind and action.target_id:
                target_kind = normalize_type(action.target_kind)
                valid_target_ids = id_registry.get(target_kind if target_kind != "marker" else "timeline_marker", set())
                if action.target_id not in valid_target_ids:
                    rejected["invalid_action_target"] += 1
                    continue

            accepted_findings.append(finding)
            if action:
                accepted_actions.append(action)
            existing_signatures.add(signature)

        return accepted_findings, accepted_actions, rejected

    async def _run_soft_critic(
        self,
        *,
        db: aiosqlite.Connection,
        run_id: str,
        world_id: str,
        note_ids: set[str],
        entities: list[dict],
        relations: list[dict],
        markers: list[dict],
        operations: list[dict],
        hard_findings: list[GuardianFinding],
        max_context_tokens: int,
    ) -> tuple[list[GuardianFinding], list[GuardianAction], dict[str, Any]]:
        if not self.backboard or not self.backboard.is_available:
            logger.info(
                "[TEMP][CANON][soft] skipped run_id=%s reason=backboard_unavailable",
                run_id,
            )
            return [], [], {"enabled": True, "executed": False, "skip_reason": "backboard_unavailable"}

        assistant_id = await self._get_world_assistant_id(db, world_id)
        if not assistant_id:
            logger.info(
                "[TEMP][CANON][soft] skipped run_id=%s world_id=%s reason=assistant_not_configured",
                run_id,
                world_id,
            )
            return [], [], {"enabled": True, "executed": False, "skip_reason": "assistant_not_configured"}

        context_pack, id_registry, context_meta = self._build_soft_critic_context_pack(
            note_ids=note_ids,
            world_id=world_id,
            entities=entities,
            relations=relations,
            markers=markers,
            operations=operations,
            hard_findings=hard_findings,
            max_context_tokens=max_context_tokens,
        )
        prompt_title = "World Canon Review"
        prompt_content = "Perform a world-level canon consistency review across entities, relations, and timeline."
        prompt = build_canon_guardian_soft_critic_prompt(
            note_title=prompt_title,
            note_content=prompt_content,
            context_pack=context_pack,
        )
        logger.info(
            "[TEMP][CANON][soft] start run_id=%s world_id=%s hard_findings=%d context_chars=%d",
            run_id,
            world_id,
            len(hard_findings),
            len(context_pack),
        )

        thread_id: str | None = None
        created_thread = False
        try:
            if not thread_id:
                thread_result = await self.backboard.create_thread(assistant_id)
                if not thread_result.success or not thread_result.id:
                    logger.info(
                        "[TEMP][CANON][soft] skipped run_id=%s reason=thread_create_failed",
                        run_id,
                    )
                    return [], [], {"enabled": True, "executed": False, "skip_reason": "thread_create_failed", **context_meta}
                thread_id = thread_result.id
                created_thread = True

            chat_result = await self.backboard.chat(thread_id=thread_id, prompt=prompt, memory="off")
            if (not chat_result.success or not chat_result.response) and not created_thread:
                # Existing note thread may have been deleted; fall back to a fresh transient thread once.
                thread_result = await self.backboard.create_thread(assistant_id)
                if thread_result.success and thread_result.id:
                    thread_id = thread_result.id
                    created_thread = True
                    chat_result = await self.backboard.chat(thread_id=thread_id, prompt=prompt, memory="off")

            if not chat_result.success or not chat_result.response:
                logger.info(
                    "[TEMP][CANON][soft] skipped run_id=%s reason=chat_failed",
                    run_id,
                )
                return [], [], {"enabled": True, "executed": False, "skip_reason": "chat_failed", **context_meta}

            raw_findings, raw_actions = self._parse_soft_critic_response(
                run_id=run_id,
                world_id=world_id,
                raw_response=chat_result.response,
            )
            accepted_findings, accepted_actions, rejected = self._validate_soft_findings(
                soft_findings=raw_findings,
                soft_actions=raw_actions,
                existing_findings=hard_findings,
                id_registry=id_registry,
            )
            meta = {
                "enabled": True,
                "executed": True,
                "raw_soft_findings": len(raw_findings),
                "accepted_soft_findings": len(accepted_findings),
                "accepted_soft_actions": len(accepted_actions),
                "rejected_soft_findings": rejected,
                **context_meta,
            }
            logger.info(
                "[TEMP][CANON][soft] complete run_id=%s raw_findings=%d accepted_findings=%d accepted_actions=%d",
                run_id,
                len(raw_findings),
                len(accepted_findings),
                len(accepted_actions),
            )
            return accepted_findings, accepted_actions, meta
        except Exception as exc:
            logger.warning("Soft critic failed for run %s: %s", run_id, exc)
            return [], [], {"enabled": True, "executed": False, "skip_reason": "exception", "error": str(exc), **context_meta}
        finally:
            if created_thread and thread_id:
                try:
                    await self.backboard.delete_thread(thread_id)
                except Exception:
                    pass

    async def create_world_scan_run(
        self,
        world_id: str,
        data: GuardianScanRequest,
    ) -> GuardianScanAccepted:
        run_id = str(uuid4())
        now = _now()
        request_json = json.dumps(data.model_dump())
        logger.info(
            "[TEMP][CANON][scan] start run_id=%s world_id=%s include_soft=%s include_llm=%s dry_run=%s",
            run_id,
            world_id,
            data.include_soft_checks,
            data.include_llm_critic,
            data.dry_run,
        )

        db = await self._get_db()
        try:
            if not await self._world_exists(db, world_id):
                raise LookupError("World not found")

            await db.execute(
                """INSERT INTO guardian_runs
                   (id, world_id, trigger_kind, status, request_json, summary_json, error, started_at, completed_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    world_id,
                    data.trigger_kind,
                    "running",
                    request_json,
                    None,
                    None,
                    now,
                    None,
                    now,
                    now,
                ),
            )
            await db.commit()
        finally:
            await db.close()

        status = "running"
        summary: dict[str, Any] | None = None
        error: str | None = None

        db = await self._get_db()
        try:
            notes = await self._list_notes(db, world_id)
            note_ids = {str(note["id"]) for note in notes if note.get("id")}
            entities = await self._list_entities(db, world_id)
            relations = await self._list_relations(db, world_id)
            markers = await self._list_markers(db, world_id)
            operations = await self._list_operations(db, world_id)
            logger.info(
                "[TEMP][CANON][scan] context_loaded run_id=%s entities=%d relations=%d markers=%d operations=%d",
                run_id,
                len(entities),
                len(relations),
                len(markers),
                len(operations),
            )

            findings, actions, summary = self._run_hard_rules(
                run_id=run_id,
                world_id=world_id,
                note_title=None,
                note_content=None,
                entities=entities,
                relations=relations,
                markers=markers,
                operations=operations,
            )
            logger.info(
                "[TEMP][CANON][scan] hard_done run_id=%s findings=%d actions=%d",
                run_id,
                len(findings),
                len(actions),
            )

            llm_meta: dict[str, Any] = {"enabled": bool(data.include_llm_critic), "executed": False}
            if data.include_soft_checks and data.include_llm_critic:
                logger.info(
                    "[TEMP][CANON][scan] soft_start run_id=%s",
                    run_id,
                )
                soft_findings, soft_actions, llm_meta = await self._run_soft_critic(
                    db=db,
                    run_id=run_id,
                    world_id=world_id,
                    note_ids=note_ids,
                    entities=entities,
                    relations=relations,
                    markers=markers,
                    operations=operations,
                    hard_findings=findings,
                    max_context_tokens=data.max_context_tokens,
                )
                findings.extend(soft_findings)
                actions.extend(soft_actions)
                logger.info(
                    "[TEMP][CANON][scan] soft_done run_id=%s findings_added=%d actions_added=%d",
                    run_id,
                    len(soft_findings),
                    len(soft_actions),
                )
            else:
                llm_meta = {
                    "enabled": bool(data.include_llm_critic),
                    "executed": False,
                    "skip_reason": "disabled",
                }
                logger.info(
                    "[TEMP][CANON][scan] soft_skipped run_id=%s include_soft=%s include_llm=%s",
                    run_id,
                    data.include_soft_checks,
                    data.include_llm_critic,
                )

            findings, actions = self._truncate_to_limit(findings, actions, data.max_findings)
            await self._store_findings_and_actions(db, world_id, run_id, findings, actions)

            severity_counts: dict[str, int] = defaultdict(int)
            for finding in findings:
                severity_counts[finding.severity] += 1

            summary = {
                **(summary or {}),
                "findings_total": len(findings),
                "actions_total": len(actions),
                "severity_counts": dict(severity_counts),
                "hard_rules_completed_at": _now(),
                "soft_critic": llm_meta,
            }
            status = "completed"
            logger.info(
                "[TEMP][CANON][scan] completed run_id=%s findings=%d actions=%d",
                run_id,
                len(findings),
                len(actions),
            )
        except Exception as exc:
            logger.exception("Canon Guardian hard-rule scan failed for run %s: %s", run_id, exc)
            status = "failed"
            error = str(exc)
            summary = summary or {"findings_total": 0, "actions_total": 0}

        completed_at = _now()
        await db.execute(
            """UPDATE guardian_runs
               SET status = ?, summary_json = ?, error = ?, completed_at = ?, updated_at = ?
               WHERE world_id = ? AND id = ?""",
            (
                status,
                json.dumps(summary or {}),
                error,
                completed_at,
                completed_at,
                world_id,
                run_id,
            ),
        )
        await db.commit()
        await db.close()
        logger.info(
            "[TEMP][CANON][scan] finalized run_id=%s status=%s error=%s",
            run_id,
            status,
            error or "",
        )

        return GuardianScanAccepted(
            status=status,
            run_id=run_id,
            world_id=world_id,
            created_at=now,
        )

    async def get_run(
        self,
        world_id: str,
        run_id: str,
        include_details: bool = True,
    ) -> GuardianRunDetail | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM guardian_runs WHERE world_id = ? AND id = ?",
                (world_id, run_id),
            )
            run_row = await cursor.fetchone()
            if not run_row:
                return None
            run = _row_to_run(dict(run_row))

            if not include_details:
                return GuardianRunDetail(**run.model_dump())

            finding_cursor = await db.execute(
                """SELECT * FROM guardian_findings
                   WHERE world_id = ? AND run_id = ?
                   ORDER BY created_at ASC, id ASC""",
                (world_id, run_id),
            )
            finding_rows = await finding_cursor.fetchall()
            findings = [_row_to_finding(dict(row)) for row in finding_rows]

            action_cursor = await db.execute(
                """SELECT * FROM guardian_actions
                   WHERE world_id = ? AND run_id = ?
                   ORDER BY created_at ASC, id ASC""",
                (world_id, run_id),
            )
            action_rows = await action_cursor.fetchall()
            actions = [_row_to_action(dict(row)) for row in action_rows]
        finally:
            await db.close()

        return GuardianRunDetail(
            **run.model_dump(),
            findings=findings,
            actions=actions,
        )

    async def dismiss_finding(
        self,
        world_id: str,
        run_id: str,
        finding_id: str,
    ) -> GuardianFindingStatusUpdate:
        db = await self._get_db()
        try:
            run_cursor = await db.execute(
                "SELECT 1 FROM guardian_runs WHERE world_id = ? AND id = ?",
                (world_id, run_id),
            )
            run_row = await run_cursor.fetchone()
            if not run_row:
                raise LookupError("Guardian run not found")

            finding_cursor = await db.execute(
                "SELECT resolution_status FROM guardian_findings WHERE world_id = ? AND run_id = ? AND id = ?",
                (world_id, run_id, finding_id),
            )
            finding_row = await finding_cursor.fetchone()
            if not finding_row:
                raise LookupError("Guardian finding not found")

            now = _now()
            await db.execute(
                """UPDATE guardian_findings
                   SET resolution_status = 'dismissed', updated_at = ?
                   WHERE world_id = ? AND run_id = ? AND id = ?""",
                (now, world_id, run_id, finding_id),
            )
            await db.execute(
                """UPDATE guardian_actions
                   SET status = 'rejected', updated_at = ?
                   WHERE world_id = ? AND run_id = ? AND finding_id = ? AND status IN ('proposed', 'accepted')""",
                (now, world_id, run_id, finding_id),
            )
            await db.execute(
                """UPDATE guardian_runs
                   SET status = CASE WHEN status = 'completed' THEN 'partial' ELSE status END,
                       updated_at = ?
                   WHERE world_id = ? AND id = ?""",
                (now, world_id, run_id),
            )
            await db.commit()
        finally:
            await db.close()

        logger.info(
            "[TEMP][CANON][scan] finding_dismissed run_id=%s finding_id=%s world_id=%s",
            run_id,
            finding_id,
            world_id,
        )
        return GuardianFindingStatusUpdate(
            status="dismissed",
            run_id=run_id,
            world_id=world_id,
            finding_id=finding_id,
            resolution_status="dismissed",
        )

    async def apply_actions(
        self,
        world_id: str,
        run_id: str,
        data: GuardianApplyRequest,
    ) -> GuardianApplyResult:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM guardian_runs WHERE world_id = ? AND id = ?",
                (world_id, run_id),
            )
            run_row = await cursor.fetchone()
            if not run_row:
                raise LookupError("Guardian run not found")

            candidate_cursor = await db.execute(
                """SELECT * FROM guardian_actions
                   WHERE world_id = ? AND run_id = ? AND status IN ('proposed', 'accepted')""",
                (world_id, run_id),
            )
            candidate_rows = await candidate_cursor.fetchall()
            candidate_actions = [_row_to_action(dict(row)) for row in candidate_rows]

            if data.apply_all:
                selected = candidate_actions
            else:
                requested_ids = set(data.action_ids)
                selected = [action for action in candidate_actions if action.id in requested_ids]

            if data.dry_run:
                return GuardianApplyResult(
                    status="dry_run",
                    run_id=run_id,
                    world_id=world_id,
                    requested_actions=len(selected),
                    accepted_actions=len(selected),
                    applied_actions=0,
                    failed_actions=0,
                    message="Dry run only. Apply engine is not implemented yet.",
                )

            selected_ids = [action.id for action in selected]
            now = _now()
            if selected_ids:
                placeholders = ", ".join("?" for _ in selected_ids)
                await db.execute(
                    f"""UPDATE guardian_actions
                        SET status = 'accepted', updated_at = ?
                        WHERE world_id = ? AND run_id = ? AND id IN ({placeholders})""",
                    [now, world_id, run_id, *selected_ids],
                )
                await db.execute(
                    "UPDATE guardian_runs SET status = 'partial', updated_at = ? WHERE world_id = ? AND id = ?",
                    (now, world_id, run_id),
                )
                await db.commit()
        finally:
            await db.close()

        return GuardianApplyResult(
            status="accepted_not_applied",
            run_id=run_id,
            world_id=world_id,
            requested_actions=len(selected),
            accepted_actions=len(selected),
            applied_actions=0,
            failed_actions=0,
            message="Actions were accepted, but execution is not implemented yet.",
        )
