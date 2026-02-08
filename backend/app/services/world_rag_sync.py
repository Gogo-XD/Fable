"""World RAG freshness orchestration (dirty tracking + conditional compiles)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.config import settings
from app.logging import get_logger
from app.models import RagCompileRequest, RagCompileResult
from app.services.world_rag_compiler import WorldRagCompilerService

logger = get_logger("services.world_rag_sync")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso8601(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


class WorldRagSyncService:
    """Track RAG freshness and trigger compiles at the right times."""

    def __init__(self, db_path: str, compiler: WorldRagCompilerService):
        self.db_path = db_path
        self.compiler = compiler
        self._world_locks: dict[str, asyncio.Lock] = {}
        self._lock_guard = asyncio.Lock()
        self._compile_tasks: dict[str, asyncio.Task] = {}
        self._task_guard = asyncio.Lock()

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _get_world_lock(self, world_id: str) -> asyncio.Lock:
        async with self._lock_guard:
            lock = self._world_locks.get(world_id)
            if lock is None:
                lock = asyncio.Lock()
                self._world_locks[world_id] = lock
            return lock

    async def _world_exists(self, db: aiosqlite.Connection, world_id: str) -> bool:
        cursor = await db.execute("SELECT 1 FROM worlds WHERE id = ?", (world_id,))
        return await cursor.fetchone() is not None

    async def _ensure_state_row(self, db: aiosqlite.Connection, world_id: str) -> None:
        now = _now()
        await db.execute(
            """INSERT INTO world_rag_state (
                   world_id, is_dirty, data_version, compiled_version, pending_change_count,
                   created_at, updated_at
               ) VALUES (?, 0, 0, 0, 0, ?, ?)
               ON CONFLICT(world_id) DO NOTHING""",
            (world_id, now, now),
        )

    async def _get_state_row(self, db: aiosqlite.Connection, world_id: str) -> dict[str, Any]:
        cursor = await db.execute("SELECT * FROM world_rag_state WHERE world_id = ?", (world_id,))
        row = await cursor.fetchone()
        if not row:
            return {}
        return dict(row)

    async def _has_compiled_documents(self, db: aiosqlite.Connection, world_id: str) -> bool:
        cursor = await db.execute(
            "SELECT 1 FROM world_rag_documents WHERE world_id = ? LIMIT 1",
            (world_id,),
        )
        return await cursor.fetchone() is not None

    def _cooldown_elapsed(self, last_attempt_at: str | None) -> bool:
        cooldown = max(int(settings.RAG_AUTO_COMPILE_COOLDOWN_SECONDS), 0)
        if cooldown == 0:
            return True
        parsed = _parse_iso8601(last_attempt_at)
        if not parsed:
            return True
        elapsed = (datetime.now(timezone.utc) - parsed).total_seconds()
        return elapsed >= cooldown

    async def _schedule_background_compile(self, world_id: str, reason: str) -> None:
        async with self._task_guard:
            existing = self._compile_tasks.get(world_id)
            if existing and not existing.done():
                return
            task = asyncio.create_task(self._run_background_compile(world_id, reason))
            self._compile_tasks[world_id] = task

    async def _run_background_compile(self, world_id: str, reason: str) -> None:
        try:
            await self.compile_if_needed(
                world_id=world_id,
                force=False,
                reason=reason,
                request=RagCompileRequest(),
            )
        except Exception:
            logger.exception("[RAG][sync] background compile failed world_id=%s reason=%s", world_id, reason)
        finally:
            async with self._task_guard:
                current = self._compile_tasks.get(world_id)
                if current and current.done():
                    self._compile_tasks.pop(world_id, None)

    async def mark_dirty(
        self,
        world_id: str,
        *,
        reason: str,
        auto_compile: bool = True,
    ) -> dict[str, Any]:
        try:
            db = await self._get_db()
            try:
                if not await self._world_exists(db, world_id):
                    return {}
                await self._ensure_state_row(db, world_id)
                now = _now()
                await db.execute(
                    """UPDATE world_rag_state
                       SET is_dirty = 1,
                           data_version = data_version + 1,
                           pending_change_count = pending_change_count + 1,
                           last_change_reason = ?,
                           last_change_at = ?,
                           updated_at = ?
                       WHERE world_id = ?""",
                    (reason, now, now, world_id),
                )
                await db.commit()
                row = await self._get_state_row(db, world_id)
            finally:
                await db.close()
        except Exception:
            logger.exception("[RAG][sync] failed to mark dirty world_id=%s reason=%s", world_id, reason)
            return {}

        threshold = max(int(settings.RAG_AUTO_COMPILE_CHANGE_THRESHOLD), 1)
        should_schedule = (
            auto_compile
            and bool(row)
            and int(row.get("pending_change_count", 0)) >= threshold
            and self._cooldown_elapsed(row.get("last_compile_attempt_at"))
            and self.compiler.backboard.is_available
        )
        if should_schedule:
            await self._schedule_background_compile(world_id, reason="change_threshold")
        return row

    async def compile_if_needed(
        self,
        *,
        world_id: str,
        force: bool = False,
        reason: str = "manual",
        request: RagCompileRequest | None = None,
    ) -> tuple[bool, RagCompileResult | None]:
        world_lock = await self._get_world_lock(world_id)
        async with world_lock:
            db = await self._get_db()
            try:
                if not await self._world_exists(db, world_id):
                    raise LookupError("World not found")
                await self._ensure_state_row(db, world_id)
                row = await self._get_state_row(db, world_id)
                has_docs = await self._has_compiled_documents(db, world_id)
                if not force and int(row.get("is_dirty", 0)) == 0 and has_docs:
                    return False, None

                start_data_version = int(row.get("data_version", 0))
                now = _now()
                await db.execute(
                    """UPDATE world_rag_state
                       SET last_compile_attempt_at = ?,
                           last_compile_status = ?,
                           last_compile_error = NULL,
                           updated_at = ?
                       WHERE world_id = ?""",
                    (now, f"running:{reason}", now, world_id),
                )
                await db.commit()
            finally:
                await db.close()

            compile_request = request or RagCompileRequest()
            try:
                result = await self.compiler.compile_world_documents(world_id=world_id, data=compile_request)
                error_text = None
            except Exception as exc:
                result = None
                error_text = str(exc)

            db = await self._get_db()
            try:
                await self._ensure_state_row(db, world_id)
                current = await self._get_state_row(db, world_id)
                current_data_version = int(current.get("data_version", 0))
                now = _now()

                if result is None:
                    await db.execute(
                        """UPDATE world_rag_state
                           SET last_compile_status = 'failed',
                               last_compile_error = ?,
                               updated_at = ?
                           WHERE world_id = ?""",
                        (error_text or "Unknown compile error", now, world_id),
                    )
                    await db.commit()
                    raise ValueError(error_text or "RAG compile failed")

                if compile_request.dry_run:
                    await db.execute(
                        """UPDATE world_rag_state
                           SET last_compile_status = ?,
                               last_compile_error = NULL,
                               updated_at = ?
                           WHERE world_id = ?""",
                        ("dry_run", now, world_id),
                    )
                    await db.commit()
                    return True, result

                if result.status == "completed":
                    if current_data_version <= start_data_version:
                        is_dirty = 0
                        pending_change_count = 0
                        compiled_version = start_data_version
                        status_text = "completed"
                    else:
                        is_dirty = 1
                        pending_change_count = max(1, current_data_version - start_data_version)
                        compiled_version = start_data_version
                        status_text = "completed_stale"
                    await db.execute(
                        """UPDATE world_rag_state
                           SET is_dirty = ?,
                               pending_change_count = ?,
                               compiled_version = ?,
                               last_compiled_at = ?,
                               last_compile_status = ?,
                               last_compile_error = NULL,
                               updated_at = ?
                           WHERE world_id = ?""",
                        (
                            is_dirty,
                            pending_change_count,
                            compiled_version,
                            now,
                            status_text,
                            now,
                            world_id,
                        ),
                    )
                elif result.status == "partial":
                    await db.execute(
                        """UPDATE world_rag_state
                           SET is_dirty = 1,
                               last_compile_status = 'partial',
                               last_compile_error = ?,
                               updated_at = ?
                           WHERE world_id = ?""",
                        (f"failed_slots={result.failed_count}", now, world_id),
                    )
                else:
                    await db.execute(
                        """UPDATE world_rag_state
                           SET last_compile_status = ?,
                               last_compile_error = NULL,
                               updated_at = ?
                           WHERE world_id = ?""",
                        (result.status, now, world_id),
                    )
                await db.commit()
                return True, result
            finally:
                await db.close()

    async def ensure_fresh_for_historian(
        self,
        world_id: str,
    ) -> tuple[bool, RagCompileResult | None, str | None]:
        try:
            compiled, result = await self.compile_if_needed(
                world_id=world_id,
                force=False,
                reason="historian_message",
                request=RagCompileRequest(),
            )
            return compiled, result, None
        except Exception as exc:
            logger.warning("[RAG][sync] historian freshness compile failed world_id=%s error=%s", world_id, exc)
            return False, None, str(exc)

    async def compile_world_documents(self, world_id: str, data: RagCompileRequest) -> RagCompileResult:
        _, result = await self.compile_if_needed(
            world_id=world_id,
            force=True,
            reason="manual_compile",
            request=data,
        )
        if not result:
            raise ValueError("RAG compile produced no result")
        return result
