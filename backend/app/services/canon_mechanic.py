"""Canon Guardian Mechanic service for generating and accepting remediation options."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from app.logging import get_logger
from app.models import (
    MechanicAcceptRequest,
    MechanicAcceptResult,
    MechanicGenerateAccepted,
    MechanicGenerateRequest,
    MechanicOption,
    MechanicRun,
    MechanicRunDetail,
    GuardianAction,
    GuardianFinding,
    normalize_type,
)
from app.services.backboard import BackboardService
from app.services.prompts import build_canon_guardian_mechanic_prompt

logger = get_logger("services.canon_mechanic")

ALLOWED_ACTION_TYPES = {
    "timeline_operation",
    "entity_patch",
    "relation_patch",
    "entity_delete",
    "relation_delete",
    "world_patch",
    "noop",
}
ALLOWED_TARGET_KINDS = {"entity", "relation", "world"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
ALLOWED_OPTION_STATUSES = {"proposed", "accepted", "rejected", "applied", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _row_to_finding(row: dict) -> GuardianFinding:
    evidence_rows = _load_json(row.get("evidence_json"), [])
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
        evidence=evidence_rows,
        suggested_action_count=row["suggested_action_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_mechanic_run(row: dict) -> MechanicRun:
    return MechanicRun(
        id=row["id"],
        world_id=row["world_id"],
        run_id=row["run_id"],
        status=row["status"],
        request=_load_json(row.get("request_json"), {}),
        summary=_load_json(row.get("summary_json"), None),
        error=row.get("error"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_mechanic_option(row: dict) -> MechanicOption:
    return MechanicOption(
        id=row["id"],
        mechanic_run_id=row["mechanic_run_id"],
        world_id=row["world_id"],
        run_id=row["run_id"],
        finding_id=row.get("finding_id"),
        option_index=row["option_index"],
        action_type=row["action_type"],
        op_type=row.get("op_type"),
        target_kind=row.get("target_kind"),
        target_id=row.get("target_id"),
        payload=_load_json(row.get("payload"), {}),
        rationale=row.get("rationale"),
        expected_outcome=row.get("expected_outcome"),
        risk_level=row["risk_level"],
        confidence=row["confidence"],
        status=row["status"],
        mapped_action_id=row.get("mapped_action_id"),
        error=row.get("error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class CanonMechanicService:
    """Service for LLM-generated remediation options for guardian findings."""

    def __init__(self, db_path: str, backboard: BackboardService | None = None):
        self.db_path = db_path
        self.backboard = backboard

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _get_world_assistant_id(self, db: aiosqlite.Connection, world_id: str) -> str | None:
        cursor = await db.execute("SELECT assistant_id FROM worlds WHERE id = ?", (world_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        assistant_id = row["assistant_id"]
        return str(assistant_id) if assistant_id else None

    async def _get_guardian_run(self, db: aiosqlite.Connection, world_id: str, run_id: str) -> dict | None:
        cursor = await db.execute(
            "SELECT * FROM guardian_runs WHERE world_id = ? AND id = ?",
            (world_id, run_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _list_findings(
        self,
        db: aiosqlite.Connection,
        world_id: str,
        run_id: str,
        finding_ids: list[str],
        include_open_findings: bool,
    ) -> list[GuardianFinding]:
        query = """SELECT * FROM guardian_findings WHERE world_id = ? AND run_id = ?"""
        params: list[Any] = [world_id, run_id]
        if finding_ids:
            placeholders = ", ".join("?" for _ in finding_ids)
            query += f" AND id IN ({placeholders})"
            params.extend(finding_ids)
        elif include_open_findings:
            query += " AND resolution_status = 'open'"
        query += " ORDER BY created_at ASC, id ASC"
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_finding(dict(row)) for row in rows]

    async def _id_registry(self, db: aiosqlite.Connection, world_id: str) -> dict[str, set[str]]:
        registry: dict[str, set[str]] = {
            "world": {world_id},
            "entity": set(),
            "relation": set(),
            "timeline_marker": set(),
            "timeline_operation": set(),
        }
        cursor = await db.execute("SELECT id FROM entities WHERE world_id = ?", (world_id,))
        registry["entity"] = {row["id"] for row in await cursor.fetchall()}
        cursor = await db.execute("SELECT id FROM relations WHERE world_id = ?", (world_id,))
        registry["relation"] = {row["id"] for row in await cursor.fetchall()}
        cursor = await db.execute("SELECT id FROM timeline_markers WHERE world_id = ?", (world_id,))
        registry["timeline_marker"] = {row["id"] for row in await cursor.fetchall()}
        cursor = await db.execute("SELECT id FROM timeline_operations WHERE world_id = ?", (world_id,))
        registry["timeline_operation"] = {row["id"] for row in await cursor.fetchall()}
        return registry

    def _build_findings_context(
        self,
        findings: list[GuardianFinding],
        max_context_tokens: int,
    ) -> str:
        max_chars = max(800, max_context_tokens * 4)
        lines = ["[open_findings]"]
        for finding in findings:
            evidence = ", ".join(f"{ev.kind}:{ev.id}" for ev in finding.evidence[:6]) or "none"
            lines.append(
                f"- finding_id={finding.id} | severity={finding.severity} | code={finding.finding_code}\n"
                f"  title={finding.title}\n"
                f"  detail={finding.detail}\n"
                f"  evidence={evidence}"
            )
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars] + "\n...<truncated>"
        return text

    def _parse_mechanic_response(
        self,
        *,
        mechanic_run_id: str,
        world_id: str,
        run_id: str,
        raw_response: str,
    ) -> list[MechanicOption]:
        text = (raw_response or "").strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        data = json.loads(text.strip())
        raw_options = data.get("options", [])
        if not isinstance(raw_options, list):
            return []

        options: list[MechanicOption] = []
        for index, item in enumerate(raw_options):
            if not isinstance(item, dict):
                continue
            action_type = normalize_type(str(item.get("action_type") or "noop"))
            if action_type not in ALLOWED_ACTION_TYPES:
                action_type = "noop"
            target_kind = item.get("target_kind")
            if target_kind is not None:
                target_kind = normalize_type(str(target_kind))
            risk_level = normalize_type(str(item.get("risk_level") or "medium"))
            if risk_level not in ALLOWED_RISK_LEVELS:
                risk_level = "medium"
            try:
                confidence = float(item.get("confidence", 0.0))
            except Exception:
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            option = MechanicOption(
                id=str(uuid4()),
                mechanic_run_id=mechanic_run_id,
                world_id=world_id,
                run_id=run_id,
                finding_id=str(item.get("finding_id") or "") or None,
                option_index=index,
                action_type=action_type,  # type: ignore[arg-type]
                op_type=normalize_type(str(item.get("op_type") or "")) or None,
                target_kind=target_kind,
                target_id=str(item.get("target_id") or "") or None,
                payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
                rationale=str(item.get("rationale") or "").strip() or None,
                expected_outcome=str(item.get("expected_outcome") or "").strip() or None,
                risk_level=risk_level,  # type: ignore[arg-type]
                confidence=confidence,
                status="proposed",
            )
            options.append(option)
        return options

    def _validate_options(
        self,
        *,
        options: list[MechanicOption],
        findings: list[GuardianFinding],
        id_registry: dict[str, set[str]],
        confidence_threshold: float,
        max_options: int,
    ) -> tuple[list[MechanicOption], dict[str, int]]:
        finding_ids = {finding.id for finding in findings}
        accepted: list[MechanicOption] = []
        rejected = {
            "invalid_finding": 0,
            "low_confidence": 0,
            "invalid_target_kind": 0,
            "invalid_target_id": 0,
            "duplicate": 0,
        }
        seen_signatures: set[tuple[str, str, str, str]] = set()
        for option in options:
            if option.finding_id not in finding_ids:
                rejected["invalid_finding"] += 1
                continue
            if option.confidence < confidence_threshold:
                rejected["low_confidence"] += 1
                continue
            target_kind = normalize_type(option.target_kind or "")
            if target_kind and target_kind not in ALLOWED_TARGET_KINDS:
                rejected["invalid_target_kind"] += 1
                continue
            if target_kind and option.target_id:
                valid_ids = id_registry.get(target_kind if target_kind != "world" else "world", set())
                if option.target_id not in valid_ids:
                    rejected["invalid_target_id"] += 1
                    continue
            signature = (
                option.finding_id or "",
                option.action_type,
                option.target_kind or "",
                json.dumps(option.payload, sort_keys=True),
            )
            if signature in seen_signatures:
                rejected["duplicate"] += 1
                continue
            seen_signatures.add(signature)
            accepted.append(option)
            if len(accepted) >= max_options:
                break
        return accepted, rejected

    async def _store_options(
        self,
        db: aiosqlite.Connection,
        mechanic_run_id: str,
        options: list[MechanicOption],
    ) -> None:
        await db.execute(
            "DELETE FROM guardian_mechanic_options WHERE mechanic_run_id = ?",
            (mechanic_run_id,),
        )
        for option in options:
            await db.execute(
                """INSERT INTO guardian_mechanic_options
                   (id, mechanic_run_id, world_id, run_id, finding_id, option_index, action_type, op_type, target_kind, target_id, payload, rationale, expected_outcome, risk_level, confidence, status, mapped_action_id, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    option.id,
                    option.mechanic_run_id,
                    option.world_id,
                    option.run_id,
                    option.finding_id,
                    option.option_index,
                    option.action_type,
                    option.op_type,
                    option.target_kind,
                    option.target_id,
                    json.dumps(option.payload),
                    option.rationale,
                    option.expected_outcome,
                    option.risk_level,
                    float(option.confidence),
                    option.status,
                    option.mapped_action_id,
                    option.error,
                    str(option.created_at),
                    str(option.updated_at),
                ),
            )

    async def create_mechanic_run(
        self,
        world_id: str,
        run_id: str,
        data: MechanicGenerateRequest,
    ) -> MechanicGenerateAccepted:
        mechanic_run_id = str(uuid4())
        now = _now()
        request_json = json.dumps(data.model_dump())
        logger.info(
            "[TEMP][CANON][mechanic] start mechanic_run_id=%s world_id=%s run_id=%s include_open=%s finding_ids=%d",
            mechanic_run_id,
            world_id,
            run_id,
            data.include_open_findings,
            len(data.finding_ids),
        )

        db = await self._get_db()
        try:
            run_row = await self._get_guardian_run(db, world_id, run_id)
            if not run_row:
                raise LookupError("Guardian run not found")

            await db.execute(
                """INSERT INTO guardian_mechanic_runs
                   (id, world_id, run_id, status, request_json, summary_json, error, started_at, completed_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mechanic_run_id,
                    world_id,
                    run_id,
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
        summary: dict[str, Any] = {}
        error: str | None = None

        db = await self._get_db()
        try:
            findings = await self._list_findings(
                db=db,
                world_id=world_id,
                run_id=run_id,
                finding_ids=data.finding_ids,
                include_open_findings=data.include_open_findings,
            )
            logger.info(
                "[TEMP][CANON][mechanic] findings_loaded mechanic_run_id=%s finding_count=%d",
                mechanic_run_id,
                len(findings),
            )
            if not findings:
                status = "completed"
                summary = {"finding_count": 0, "raw_options": 0, "accepted_options": 0, "skip_reason": "no_findings"}
                logger.info(
                    "[TEMP][CANON][mechanic] skipped mechanic_run_id=%s reason=no_findings",
                    mechanic_run_id,
                )
            elif not self.backboard or not self.backboard.is_available:
                status = "failed"
                error = "Backboard service is not available"
                summary = {"finding_count": len(findings), "raw_options": 0, "accepted_options": 0}
                logger.info(
                    "[TEMP][CANON][mechanic] failed mechanic_run_id=%s reason=backboard_unavailable",
                    mechanic_run_id,
                )
            else:
                assistant_id = await self._get_world_assistant_id(db, world_id)
                if not assistant_id:
                    status = "failed"
                    error = "World has no Backboard assistant configured"
                    summary = {"finding_count": len(findings), "raw_options": 0, "accepted_options": 0}
                    logger.info(
                        "[TEMP][CANON][mechanic] failed mechanic_run_id=%s reason=assistant_not_configured",
                        mechanic_run_id,
                    )
                else:
                    context = self._build_findings_context(findings, data.max_context_tokens)
                    prompt = build_canon_guardian_mechanic_prompt(
                        world_id=world_id,
                        run_id=run_id,
                        findings_context=context,
                    )
                    logger.info(
                        "[TEMP][CANON][mechanic] llm_start mechanic_run_id=%s context_chars=%d",
                        mechanic_run_id,
                        len(context),
                    )
                    thread_id: str | None = None
                    raw_options: list[MechanicOption] = []
                    accepted_options: list[MechanicOption] = []
                    rejected_meta: dict[str, int] = {}
                    try:
                        thread_result = await self.backboard.create_thread(assistant_id)
                        if not thread_result.success or not thread_result.id:
                            raise ValueError("Failed to create mechanic thread")
                        thread_id = thread_result.id
                        chat_result = await self.backboard.chat(thread_id=thread_id, prompt=prompt, memory="off")
                        if not chat_result.success or not chat_result.response:
                            raise ValueError("Mechanic LLM returned no response")

                        raw_options = self._parse_mechanic_response(
                            mechanic_run_id=mechanic_run_id,
                            world_id=world_id,
                            run_id=run_id,
                            raw_response=chat_result.response,
                        )
                        id_registry = await self._id_registry(db, world_id)
                        accepted_options, rejected_meta = self._validate_options(
                            options=raw_options,
                            findings=findings,
                            id_registry=id_registry,
                            confidence_threshold=data.confidence_threshold,
                            max_options=data.max_options,
                        )
                        await self._store_options(db, mechanic_run_id, accepted_options)
                        status = "completed"
                        summary = {
                            "finding_count": len(findings),
                            "raw_options": len(raw_options),
                            "accepted_options": len(accepted_options),
                            "rejected_options": rejected_meta,
                        }
                        logger.info(
                            "[TEMP][CANON][mechanic] llm_complete mechanic_run_id=%s raw_options=%d accepted_options=%d",
                            mechanic_run_id,
                            len(raw_options),
                            len(accepted_options),
                        )
                    finally:
                        if thread_id:
                            try:
                                await self.backboard.delete_thread(thread_id)
                            except Exception:
                                pass
        except Exception as exc:
            logger.exception("Mechanic generation failed for run %s/%s: %s", run_id, mechanic_run_id, exc)
            status = "failed"
            error = str(exc)
            if not summary:
                summary = {"finding_count": 0, "raw_options": 0, "accepted_options": 0}

        completed_at = _now()
        await db.execute(
            """UPDATE guardian_mechanic_runs
               SET status = ?, summary_json = ?, error = ?, completed_at = ?, updated_at = ?
               WHERE world_id = ? AND id = ?""",
            (
                status,
                json.dumps(summary or {}),
                error,
                completed_at,
                completed_at,
                world_id,
                mechanic_run_id,
            ),
        )
        await db.commit()
        await db.close()
        logger.info(
            "[TEMP][CANON][mechanic] finalized mechanic_run_id=%s status=%s error=%s",
            mechanic_run_id,
            status,
            error or "",
        )

        return MechanicGenerateAccepted(
            status=status,
            mechanic_run_id=mechanic_run_id,
            world_id=world_id,
            run_id=run_id,
            created_at=now,
        )

    async def get_mechanic_run(
        self,
        world_id: str,
        mechanic_run_id: str,
        include_options: bool = True,
    ) -> MechanicRunDetail | None:
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM guardian_mechanic_runs WHERE world_id = ? AND id = ?",
                (world_id, mechanic_run_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            run = _row_to_mechanic_run(dict(row))

            options: list[MechanicOption] = []
            if include_options:
                option_cursor = await db.execute(
                    """SELECT * FROM guardian_mechanic_options
                       WHERE world_id = ? AND mechanic_run_id = ?
                       ORDER BY option_index ASC, created_at ASC, id ASC""",
                    (world_id, mechanic_run_id),
                )
                option_rows = await option_cursor.fetchall()
                options = [_row_to_mechanic_option(dict(option_row)) for option_row in option_rows]
        finally:
            await db.close()

        return MechanicRunDetail(**run.model_dump(), options=options)

    async def _apply_entity_patch(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
        now: str,
    ) -> tuple[bool, str | None]:
        if not option.target_id:
            return False, "entity_patch requires target_id"

        payload = dict(option.payload or {})
        fields: dict[str, Any] = {}

        if isinstance(payload.get("name"), str):
            name = payload["name"].strip()
            if name:
                fields["name"] = name
        if payload.get("type") is not None:
            normalized_type = normalize_type(str(payload.get("type") or ""))
            if normalized_type:
                fields["type"] = normalized_type
        if "subtype" in payload:
            subtype_raw = payload.get("subtype")
            if subtype_raw is None or str(subtype_raw).strip() == "":
                fields["subtype"] = None
            else:
                fields["subtype"] = normalize_type(str(subtype_raw))
        if isinstance(payload.get("aliases"), list):
            aliases = [str(value).strip() for value in payload["aliases"] if str(value).strip()]
            fields["aliases"] = json.dumps(aliases)
        if "context" in payload and (payload.get("context") is None or isinstance(payload.get("context"), str)):
            fields["context"] = payload.get("context")
        if "summary" in payload and (payload.get("summary") is None or isinstance(payload.get("summary"), str)):
            fields["summary"] = payload.get("summary")
        if isinstance(payload.get("tags"), list):
            tags = [str(value).strip() for value in payload["tags"] if str(value).strip()]
            fields["tags"] = json.dumps(tags)
        if "image_url" in payload and (payload.get("image_url") is None or isinstance(payload.get("image_url"), str)):
            fields["image_url"] = payload.get("image_url")
        if isinstance(payload.get("status"), str):
            status = payload["status"].strip()
            if status:
                fields["status"] = status

        fields["source"] = "ai"
        fields["updated_at"] = now
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [option.target_id, world_id]
        cursor = await db.execute(
            f"UPDATE entities SET {set_clause} WHERE id = ? AND world_id = ?",
            values,
        )
        if cursor.rowcount <= 0:
            return False, f"Entity target {option.target_id} not found"
        return True, None

    async def _apply_relation_patch(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
        now: str,
    ) -> tuple[bool, str | None]:
        if not option.target_id:
            return False, "relation_patch requires target_id"

        payload = dict(option.payload or {})
        fields: dict[str, Any] = {}
        if payload.get("type") is not None:
            normalized_type = normalize_type(str(payload.get("type") or ""))
            if normalized_type:
                fields["type"] = normalized_type
        if "context" in payload and (payload.get("context") is None or isinstance(payload.get("context"), str)):
            fields["context"] = payload.get("context")
        if payload.get("weight") is not None:
            try:
                weight = float(payload["weight"])
                fields["weight"] = max(0.0, min(1.0, weight))
            except Exception:
                return False, "relation_patch weight must be numeric"

        fields["source"] = "ai"
        fields["updated_at"] = now
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [option.target_id, world_id]
        cursor = await db.execute(
            f"UPDATE relations SET {set_clause} WHERE id = ? AND world_id = ?",
            values,
        )
        if cursor.rowcount <= 0:
            return False, f"Relation target {option.target_id} not found"
        return True, None

    async def _apply_entity_delete(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
    ) -> tuple[bool, str | None]:
        if not option.target_id:
            return False, "entity_delete requires target_id"

        cursor = await db.execute(
            "DELETE FROM entities WHERE id = ? AND world_id = ?",
            (option.target_id, world_id),
        )
        if cursor.rowcount <= 0:
            return False, f"Entity target {option.target_id} not found"
        return True, None

    async def _apply_relation_delete(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
    ) -> tuple[bool, str | None]:
        if not option.target_id:
            return False, "relation_delete requires target_id"

        cursor = await db.execute(
            "DELETE FROM relations WHERE id = ? AND world_id = ?",
            (option.target_id, world_id),
        )
        if cursor.rowcount <= 0:
            return False, f"Relation target {option.target_id} not found"
        return True, None

    async def _apply_world_patch(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
        now: str,
    ) -> tuple[bool, str | None]:
        payload = dict(option.payload or {})
        fields: dict[str, Any] = {}
        if isinstance(payload.get("name"), str):
            name = payload["name"].strip()
            if name:
                fields["name"] = name
        if "description" in payload and (payload.get("description") is None or isinstance(payload.get("description"), str)):
            fields["description"] = payload.get("description")
        if isinstance(payload.get("entity_types"), list):
            entity_types = [normalize_type(str(value)) for value in payload["entity_types"] if str(value).strip()]
            fields["entity_types"] = json.dumps(entity_types)
        if isinstance(payload.get("relation_types"), list):
            relation_types = [normalize_type(str(value)) for value in payload["relation_types"] if str(value).strip()]
            fields["relation_types"] = json.dumps(relation_types)

        if not fields:
            return True, None

        fields["updated_at"] = now
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [world_id]
        cursor = await db.execute(
            f"UPDATE worlds SET {set_clause} WHERE id = ?",
            values,
        )
        if cursor.rowcount <= 0:
            return False, f"World target {world_id} not found"
        return True, None

    async def _resolve_marker_for_timeline_action(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        payload: dict[str, Any],
    ) -> str | None:
        marker_id = str(payload.get("marker_id") or "").strip()
        if marker_id:
            cursor = await db.execute(
                "SELECT id FROM timeline_markers WHERE world_id = ? AND id = ?",
                (world_id, marker_id),
            )
            row = await cursor.fetchone()
            return marker_id if row else None

        cursor = await db.execute(
            """SELECT id FROM timeline_markers
               WHERE world_id = ? AND placement_status = 'placed'
               ORDER BY sort_key DESC, created_at DESC, id DESC
               LIMIT 1""",
            (world_id,),
        )
        row = await cursor.fetchone()
        if row:
            return str(row["id"])
        cursor = await db.execute(
            "SELECT id FROM timeline_markers WHERE world_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (world_id,),
        )
        row = await cursor.fetchone()
        return str(row["id"]) if row else None

    async def _validate_timeline_target(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        target_kind: str,
        target_id: str | None,
    ) -> tuple[bool, str | None]:
        if target_kind == "world":
            return True, None
        if not target_id:
            return False, f"{target_kind} timeline_operation requires target_id"

        table = "entities" if target_kind == "entity" else "relations"
        cursor = await db.execute(
            f"SELECT id FROM {table} WHERE world_id = ? AND id = ?",
            (world_id, target_id),
        )
        row = await cursor.fetchone()
        if not row:
            return False, f"{target_kind} target {target_id} not found"
        return True, None

    async def _apply_timeline_operation(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
        now: str,
    ) -> tuple[bool, str | None]:
        payload = dict(option.payload or {})
        marker_id = await self._resolve_marker_for_timeline_action(db, world_id=world_id, payload=payload)
        if not marker_id:
            return False, "timeline_operation requires an existing timeline marker"

        op_type = normalize_type(option.op_type or str(payload.get("op_type") or ""))
        if not op_type:
            return False, "timeline_operation requires op_type"

        target_kind = normalize_type(option.target_kind or str(payload.get("target_kind") or "world"))
        if target_kind not in ALLOWED_TARGET_KINDS:
            return False, f"Unsupported target_kind for timeline_operation: {target_kind}"
        target_id = option.target_id or str(payload.get("target_id") or "") or None
        valid_target, target_error = await self._validate_timeline_target(
            db,
            world_id=world_id,
            target_kind=target_kind,
            target_id=target_id,
        )
        if not valid_target:
            return False, target_error

        op_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {
            key: value
            for key, value in payload.items()
            if key not in {"marker_id", "op_type", "target_kind", "target_id"}
        }

        cursor = await db.execute(
            "SELECT COALESCE(MAX(order_index), -1) + 1 AS next_index FROM timeline_operations WHERE world_id = ? AND marker_id = ?",
            (world_id, marker_id),
        )
        row = await cursor.fetchone()
        next_index = int(row["next_index"]) if row else 0

        await db.execute(
            """INSERT INTO timeline_operations
               (id, world_id, marker_id, op_type, target_kind, target_id, payload, order_index, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                world_id,
                marker_id,
                op_type,
                target_kind,
                target_id,
                json.dumps(op_payload),
                next_index,
                now,
                now,
            ),
        )
        return True, None

    async def _apply_mechanic_option(
        self,
        db: aiosqlite.Connection,
        *,
        world_id: str,
        option: MechanicOption,
        now: str,
    ) -> tuple[bool, str | None]:
        action_type = normalize_type(option.action_type or "")
        if action_type == "noop":
            return True, None
        if action_type == "entity_patch":
            return await self._apply_entity_patch(db, world_id=world_id, option=option, now=now)
        if action_type == "relation_patch":
            return await self._apply_relation_patch(db, world_id=world_id, option=option, now=now)
        if action_type == "entity_delete":
            return await self._apply_entity_delete(db, world_id=world_id, option=option)
        if action_type == "relation_delete":
            return await self._apply_relation_delete(db, world_id=world_id, option=option)
        if action_type == "world_patch":
            return await self._apply_world_patch(db, world_id=world_id, option=option, now=now)
        if action_type == "timeline_operation":
            return await self._apply_timeline_operation(db, world_id=world_id, option=option, now=now)
        return False, f"Unsupported action_type: {action_type}"

    async def accept_options(
        self,
        world_id: str,
        mechanic_run_id: str,
        data: MechanicAcceptRequest,
    ) -> MechanicAcceptResult:
        logger.info(
            "[TEMP][CANON][mechanic] accept_start mechanic_run_id=%s world_id=%s accept_all=%s option_ids=%d create_actions=%s apply_immediately=%s",
            mechanic_run_id,
            world_id,
            data.accept_all,
            len(data.option_ids),
            data.create_guardian_actions,
            data.apply_immediately,
        )
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM guardian_mechanic_runs WHERE world_id = ? AND id = ?",
                (world_id, mechanic_run_id),
            )
            run_row = await cursor.fetchone()
            if not run_row:
                raise LookupError("Mechanic run not found")
            run = _row_to_mechanic_run(dict(run_row))

            option_cursor = await db.execute(
                """SELECT * FROM guardian_mechanic_options
                   WHERE world_id = ? AND mechanic_run_id = ? AND status IN ('proposed', 'accepted')""",
                (world_id, mechanic_run_id),
            )
            option_rows = await option_cursor.fetchall()
            candidate_options = [_row_to_mechanic_option(dict(row)) for row in option_rows]

            if data.accept_all:
                selected = candidate_options
            else:
                option_ids = set(data.option_ids)
                selected = [option for option in candidate_options if option.id in option_ids]

            if not selected:
                logger.info(
                    "[TEMP][CANON][mechanic] accept_noop mechanic_run_id=%s reason=no_options_selected",
                    mechanic_run_id,
                )
                return MechanicAcceptResult(
                    status="no_options_selected",
                    mechanic_run_id=mechanic_run_id,
                    world_id=world_id,
                    run_id=run.run_id,
                    requested_options=0,
                    accepted_options=0,
                    actions_created=0,
                    actions_failed=0,
                    applied_options=0,
                    apply_failures=0,
                    message="No matching proposed mechanic options were selected.",
                )

            actions_created = 0
            actions_failed = 0
            applied_options = 0
            apply_failures = 0
            now = _now()
            option_status_by_id = {option.id: option.status for option in selected}
            action_id_by_option_id: dict[str, str] = {}
            selected_ids = [option.id for option in selected]
            proposed_selected_ids = [option.id for option in selected if option.status == "proposed"]
            if proposed_selected_ids:
                placeholders = ", ".join("?" for _ in proposed_selected_ids)
                await db.execute(
                    f"""UPDATE guardian_mechanic_options
                        SET status = 'accepted', error = NULL, updated_at = ?
                        WHERE world_id = ? AND mechanic_run_id = ? AND id IN ({placeholders})""",
                    [now, world_id, mechanic_run_id, *proposed_selected_ids],
                )

            if data.create_guardian_actions:
                for option in selected:
                    if option_status_by_id.get(option.id) != "proposed":
                        continue
                    action_id = str(uuid4())
                    try:
                        await db.execute(
                            """INSERT INTO guardian_actions
                               (id, run_id, finding_id, world_id, action_type, op_type, target_kind, target_id, payload, rationale, status, error, created_at, updated_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                action_id,
                                option.run_id,
                                option.finding_id,
                                world_id,
                                option.action_type,
                                option.op_type,
                                option.target_kind,
                                option.target_id,
                                json.dumps(option.payload),
                                option.rationale,
                                "accepted",
                                None,
                                now,
                                now,
                            ),
                        )
                        action_id_by_option_id[option.id] = action_id
                        await db.execute(
                            """UPDATE guardian_mechanic_options
                               SET mapped_action_id = ?, updated_at = ?
                               WHERE id = ? AND mechanic_run_id = ?""",
                            (action_id, now, option.id, mechanic_run_id),
                        )
                        actions_created += 1
                    except Exception:
                        actions_failed += 1
                        await db.execute(
                            """UPDATE guardian_mechanic_options
                               SET status = 'failed', error = ?, updated_at = ?
                                WHERE id = ? AND mechanic_run_id = ?""",
                            ("Failed to create guardian action.", now, option.id, mechanic_run_id),
                        )

            if data.apply_immediately:
                applied_finding_ids: set[str] = set()
                for option in selected:
                    if option.status not in {"proposed", "accepted"}:
                        continue
                    option_now = _now()
                    success, error_text = await self._apply_mechanic_option(
                        db,
                        world_id=world_id,
                        option=option,
                        now=option_now,
                    )
                    if success:
                        applied_options += 1
                        await db.execute(
                            """UPDATE guardian_mechanic_options
                               SET status = 'applied', error = NULL, updated_at = ?
                               WHERE world_id = ? AND mechanic_run_id = ? AND id = ?""",
                            (option_now, world_id, mechanic_run_id, option.id),
                        )
                        if option.finding_id:
                            applied_finding_ids.add(option.finding_id)
                        mapped_action_id = option.mapped_action_id or action_id_by_option_id.get(option.id)
                        if mapped_action_id:
                            await db.execute(
                                """UPDATE guardian_actions
                                   SET status = 'applied', error = NULL, updated_at = ?
                                   WHERE world_id = ? AND id = ?""",
                                (option_now, world_id, mapped_action_id),
                            )
                    else:
                        apply_failures += 1
                        failure_reason = error_text or "Failed to apply mechanic option."
                        await db.execute(
                            """UPDATE guardian_mechanic_options
                               SET status = 'failed', error = ?, updated_at = ?
                               WHERE world_id = ? AND mechanic_run_id = ? AND id = ?""",
                            (failure_reason, option_now, world_id, mechanic_run_id, option.id),
                        )
                        mapped_action_id = option.mapped_action_id or action_id_by_option_id.get(option.id)
                        if mapped_action_id:
                            await db.execute(
                                """UPDATE guardian_actions
                                   SET status = 'failed', error = ?, updated_at = ?
                                   WHERE world_id = ? AND id = ?""",
                                (failure_reason, option_now, world_id, mapped_action_id),
                            )
                if applied_finding_ids:
                    placeholders = ", ".join("?" for _ in applied_finding_ids)
                    await db.execute(
                        f"""UPDATE guardian_findings
                            SET resolution_status = 'applied', updated_at = ?
                            WHERE world_id = ? AND run_id = ? AND id IN ({placeholders})""",
                        [_now(), world_id, run.run_id, *applied_finding_ids],
                    )

            remaining_cursor = await db.execute(
                """SELECT COUNT(1) AS count
                   FROM guardian_mechanic_options
                   WHERE world_id = ? AND mechanic_run_id = ? AND status = 'proposed'""",
                (world_id, mechanic_run_id),
            )
            remaining_row = await remaining_cursor.fetchone()
            remaining_proposed = int(remaining_row["count"]) if remaining_row else 0
            run_status = "completed" if remaining_proposed == 0 else "partial"
            await db.execute(
                """UPDATE guardian_mechanic_runs
                   SET status = ?, updated_at = ?
                    WHERE world_id = ? AND id = ?""",
                (run_status, now, world_id, mechanic_run_id),
            )
            await db.commit()
        finally:
            await db.close()
        logger.info(
            "[TEMP][CANON][mechanic] accept_complete mechanic_run_id=%s selected=%d actions_created=%d actions_failed=%d applied_options=%d apply_failures=%d",
            mechanic_run_id,
            len(selected),
            actions_created,
            actions_failed,
            applied_options,
            apply_failures,
        )

        status = "accepted"
        message: str | None = None
        if data.apply_immediately:
            if applied_options > 0 and apply_failures == 0:
                status = "applied"
            elif applied_options > 0:
                status = "applied_partial"
                message = "Some selected options were applied, but one or more failed."
            else:
                status = "applied_none"
                message = "No selected options could be applied."

        return MechanicAcceptResult(
            status=status,
            mechanic_run_id=mechanic_run_id,
            world_id=world_id,
            run_id=run.run_id,
            requested_options=len(selected),
            accepted_options=len(selected),
            actions_created=actions_created,
            actions_failed=actions_failed,
            applied_options=applied_options,
            apply_failures=apply_failures,
            message=message,
        )
