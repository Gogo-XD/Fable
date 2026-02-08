"""Historian NPC chat service."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

import aiosqlite

from app.logging import get_logger
from app.models import HistorianMessageResponse
from app.services.backboard import BackboardService
from app.services.historian_context import HistorianContextCompiler
from app.services.prompts import build_historian_turn_prompt
from app.services.timeline import TimelineService
from app.services.world_rag_sync import WorldRagSyncService

logger = get_logger("services.historian")

_FOLLOW_UP_PREFIXES: tuple[str, ...] = (
    "and ",
    "also ",
    "what about ",
    "how about ",
    "then ",
    "so ",
)
_FOLLOW_UP_PHRASES: tuple[str, ...] = (
    "compared to",
    "compare to",
    "difference between",
    "same as",
    "as above",
    "as before",
    "previous answer",
    "earlier answer",
)
_FOLLOW_UP_PRONOUN_PATTERN = re.compile(
    r"\b(he|she|they|him|her|them|his|hers|their|it|its|this|that|these|those|former|latter)\b",
    re.IGNORECASE,
)
_PRIMARY_TARGET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*who\s+is\s+(.+?)[\?\.\!\s]*$", re.IGNORECASE),
    re.compile(r"^\s*who\s+was\s+(.+?)[\?\.\!\s]*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+happened\s+to\s+(.+?)[\?\.\!\s]*$", re.IGNORECASE),
    re.compile(r"^\s*tell\s+me\s+about\s+(.+?)[\?\.\!\s]*$", re.IGNORECASE),
    re.compile(r"^\s*describe\s+(.+?)[\?\.\!\s]*$", re.IGNORECASE),
)
_MARKDOWN_HEADER_PATTERN = re.compile(r"^\s*#{1,6}\s*")
_MARKDOWN_LIST_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)")
_CODE_SPAN_PATTERN = re.compile(r"`([^`]*)`")
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_INLINE_REF_PATTERN = re.compile(
    r"\[(?:entity|relation|marker|note|operation|rag_document|rag_slot):[^\]]+\]"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _looks_like_follow_up_question(message: str) -> bool:
    text = " ".join((message or "").strip().split())
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith(_FOLLOW_UP_PREFIXES):
        return True
    if any(phrase in lowered for phrase in _FOLLOW_UP_PHRASES):
        return True
    return bool(_FOLLOW_UP_PRONOUN_PATTERN.search(text))


def _extract_primary_target(message: str) -> str | None:
    text = " ".join((message or "").strip().split())
    if not text:
        return None
    for pattern in _PRIMARY_TARGET_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        target = match.group(1).strip(" \"'`")
        if target:
            return target
    return None


def _to_spoken_response(text: str, *, keep_inline_refs: bool) -> str:
    raw = str(text or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""

    lines = raw.split("\n")
    normalized: list[str] = []
    markdownish_line_count = 0
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            if normalized and normalized[-1] != "":
                normalized.append("")
            continue

        if _MARKDOWN_HEADER_PATTERN.match(cleaned):
            cleaned = _MARKDOWN_HEADER_PATTERN.sub("", cleaned)
            markdownish_line_count += 1
        if _MARKDOWN_LIST_PATTERN.match(cleaned):
            cleaned = _MARKDOWN_LIST_PATTERN.sub("", cleaned)
            markdownish_line_count += 1

        cleaned = cleaned.replace("**", "").replace("__", "")
        cleaned = _CODE_SPAN_PATTERN.sub(r"\1", cleaned)
        cleaned = _LINK_PATTERN.sub(r"\1", cleaned)
        if not keep_inline_refs:
            cleaned = _INLINE_REF_PATTERN.sub("", cleaned)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            normalized.append(cleaned)

    if not normalized:
        return ""

    if markdownish_line_count >= 2:
        return re.sub(r"\s+", " ", " ".join(normalized)).strip()

    compact: list[str] = []
    for line in normalized:
        if line == "":
            if compact and compact[-1] != "":
                compact.append("")
            continue
        compact.append(line)
    return "\n".join(compact).strip()


class HistorianService:
    """Chat with a world-specific Historian assistant thread."""

    def __init__(
        self,
        db_path: str,
        backboard: BackboardService,
        rag_sync: WorldRagSyncService,
        timeline_service: TimelineService,
    ):
        self.db_path = db_path
        self.backboard = backboard
        self.rag_sync = rag_sync
        self.context_compiler = HistorianContextCompiler(
            db_path=db_path,
            timeline_service=timeline_service,
        )

    async def _get_db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _get_world(self, world_id: str) -> dict[str, Any] | None:
        db = await self._get_db()
        try:
            cursor = await db.execute("SELECT id, assistant_id FROM worlds WHERE id = ?", (world_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await db.close()

    async def send_message(
        self,
        *,
        world_id: str,
        message: str,
        thread_id: str | None = None,
    ) -> HistorianMessageResponse:
        if not self.backboard.is_available:
            raise ValueError("Backboard service is not available")

        world = await self._get_world(world_id)
        if not world:
            raise LookupError("World not found")
        assistant_id = str(world.get("assistant_id") or "").strip()
        if not assistant_id:
            raise ValueError(f"World {world_id} has no Backboard assistant configured")

        rag_refreshed, rag_result, rag_error = await self.rag_sync.ensure_fresh_for_historian(world_id)

        active_thread_id = (thread_id or "").strip() or None
        if not active_thread_id:
            thread = await self.backboard.create_thread(assistant_id)
            if not thread.success or not thread.id:
                raise ValueError("Failed to create historian thread")
            active_thread_id = thread.id

        context_result = await self.context_compiler.build_context(
            world_id=world_id,
            question=message,
        )

        historian_prompt = build_historian_turn_prompt(
            user_message=message,
            allow_history_reference=_looks_like_follow_up_question(message),
            primary_target=_extract_primary_target(message),
            intent=context_result.intent,
            intent_confidence=context_result.confidence,
            intent_strategy=context_result.strategy,
            packs_used=list(context_result.packs_used),
            evidence_refs=list(context_result.evidence_refs),
            context_pack=context_result.context_pack,
        )

        chat_result = await self.backboard.chat(
            thread_id=active_thread_id,
            prompt=historian_prompt,
            memory=True,
        )
        if (not chat_result.success or not chat_result.response) and thread_id:
            # Existing thread may have been deleted. Retry once with a new thread.
            retry_thread = await self.backboard.create_thread(assistant_id)
            if retry_thread.success and retry_thread.id:
                active_thread_id = retry_thread.id
                chat_result = await self.backboard.chat(
                    thread_id=active_thread_id,
                    prompt=historian_prompt,
                    memory=True,
                )

        if not chat_result.success or not chat_result.response:
            raise ValueError(chat_result.error or "Historian chat failed")

        spoken_response = _to_spoken_response(
            chat_result.response,
            keep_inline_refs=context_result.intent == "provenance_citation",
        )

        logger.info(
            "[Historian] world_id=%s intent=%s confidence=%.2f packs=%s rag_refreshed=%s rag_status=%s at=%s",
            world_id,
            context_result.intent,
            context_result.confidence,
            ",".join(context_result.packs_used),
            rag_refreshed,
            rag_result.status if rag_result else None,
            _now(),
        )

        return HistorianMessageResponse(
            thread_id=active_thread_id,
            response=spoken_response,
            rag_refreshed=rag_refreshed,
            rag_compile_status=rag_result.status if rag_result else None,
            rag_compile_error=rag_error,
        )
