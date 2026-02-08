"""
Backboard.io integration service.

Handles assistant management, thread lifecycle, document storage, and chat.
Analysis/extraction logic lives in LoreService — this is the transport layer.
"""

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from backboard import BackboardClient

from app.config import settings
from app.logging import get_logger
from app.models import (
    AssistantCreated, ThreadCreated, ThreadDeleted,
    DocumentCreated, DocumentUpdated, ChatResponse,
)
from app.services.prompts import build_world_assistant_prompt

logger = get_logger('services.backboard')
_T = TypeVar("_T")

class BackboardService:
    """Service for interacting with Backboard.io."""

    def __init__(self):
        self.client = None
        self._initialized = False

    async def initialize(self):
        if not settings.BACKBOARD_API_KEY:
            logger.warning("BACKBOARD_API_KEY not set - AI features will be disabled")
            return

        try:
            self.client = BackboardClient(api_key=settings.BACKBOARD_API_KEY)
            self._initialized = True
            logger.info("Backboard client initialized")
        except ImportError:
            logger.warning("backboard package not installed - run: pip install backboard")
        except Exception as e:
            logger.error(f"Failed to initialize Backboard: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized and self.client is not None

    def _is_transient_error(self, error: Exception) -> bool:
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            return True

        message = str(error).lower()
        transient_tokens = (
            "timed out",
            "timeout",
            "rate limit",
            "too many requests",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "connection refused",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "429",
            "502",
            "503",
            "504",
        )
        return any(token in message for token in transient_tokens)

    def _is_indexing_in_progress_error(self, error_or_message: Exception | str) -> bool:
        message = str(error_or_message).lower()
        indexing_tokens = (
            "cannot send message while documents are still being indexed",
            "documents are still being indexed",
            "still being indexed",
            "assistant-level documents",
            ": processing",
        )
        return any(token in message for token in indexing_tokens)

    async def _run_with_retry(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[_T]],
    ) -> _T:
        max_retries = max(int(settings.BACKBOARD_MAX_RETRIES), 0)
        total_attempts = max_retries + 1
        base_delay = max(float(settings.BACKBOARD_RETRY_BASE_SECONDS), 0.0)
        max_delay = max(float(settings.BACKBOARD_RETRY_MAX_SECONDS), base_delay)

        attempt = 1
        while True:
            try:
                return await operation()
            except Exception as error:
                should_retry = attempt < total_attempts and self._is_transient_error(error)
                if not should_retry:
                    raise

                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                logger.warning(
                    "Backboard %s failed (attempt %d/%d): %s. Retrying in %.2fs",
                    operation_name,
                    attempt,
                    total_attempts,
                    error,
                    delay,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                attempt += 1

    # ── Assistants ──

    async def create_world_assistant(self, world_name: str, description: str = "") -> AssistantCreated:
        if not self.is_available:
            return AssistantCreated(success=False)

        try:
            assistant = await self.client.create_assistant(
                name=f"World: {world_name}",
                embedding_provider=settings.EMBEDDING_PROVIDER,
                embedding_model_name=settings.EMBEDDING_MODEL,
                description=build_world_assistant_prompt(world_name, description)
            )
            logger.info(f"Created world assistant: {assistant.assistant_id}")
            return AssistantCreated(success=True, id=str(assistant.assistant_id))
        except Exception as e:
            logger.error(f"Failed to create world assistant: {e}")
            return AssistantCreated(success=False)

    # ── Threads ──

    async def create_thread(self, assistant_id: str) -> ThreadCreated:
        if not self.is_available:
            return ThreadCreated(success=False)

        try:
            thread = await self._run_with_retry(
                "create_thread",
                lambda: self.client.create_thread(assistant_id=assistant_id),
            )
            return ThreadCreated(success=True, id=str(thread.thread_id))
        except Exception as e:
            logger.error(f"Failed to create thread for assistant {assistant_id}: {e}")
            return ThreadCreated(success=False)

    async def delete_thread(self, thread_id: str) -> ThreadDeleted:
        if not self.is_available:
            return ThreadDeleted(success=False)

        try:
            await self.client.delete_thread(thread_id=thread_id)
            return ThreadDeleted(success=True)
        except Exception as e:
            logger.error(f"Failed to delete thread: {e}")
            return ThreadDeleted(success=False)

    # ── Chat ──

    def _normalize_memory_mode(self, memory: bool | str) -> str:
        if isinstance(memory, bool):
            return "Auto" if memory else "off"
        raw = str(memory or "").strip().lower()
        if raw in {"auto", "on", "true", "readwrite", "read_write"}:
            return "Auto"
        if raw in {"readonly", "read_only", "read-only"}:
            return "Readonly"
        return "off"

    async def chat(self, thread_id: str, prompt: str, memory: bool | str = False) -> ChatResponse:
        if not self.is_available:
            return ChatResponse(success=False, error="Backboard service unavailable")

        max_wait_seconds = max(int(settings.BACKBOARD_INDEXING_WAIT_SECONDS), 0)
        retry_delay_seconds = max(float(settings.BACKBOARD_INDEXING_RETRY_SECONDS), 0.1)
        llm_provider = str(getattr(settings, "LLM_PROVIDER", "") or "").strip()
        model_name = str(getattr(settings, "MODEL_NAME", "") or "").strip()
        memory_mode = self._normalize_memory_mode(memory)
        add_message_kwargs: dict[str, Any] = {
            "thread_id": thread_id,
            "content": prompt,
        }
        add_message_kwargs["memory"] = memory_mode
        if llm_provider:
            add_message_kwargs["llm_provider"] = llm_provider
        if model_name:
            add_message_kwargs["model_name"] = model_name
        logger.debug(
            "Backboard add_message routing thread=%s provider=%s model=%s memory=%s",
            thread_id,
            llm_provider or "(default)",
            model_name or "(default)",
            memory_mode,
        )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_wait_seconds

        while True:
            try:
                response = await self._run_with_retry(
                    "add_message",
                    lambda: self.client.add_message(**add_message_kwargs),
                )
                response_model_provider = str(getattr(response, "model_provider", "") or "").strip() or None
                response_model_name = str(getattr(response, "model_name", "") or "").strip() or None
                input_tokens = getattr(response, "input_tokens", None)
                output_tokens = getattr(response, "output_tokens", None)
                total_tokens = getattr(response, "total_tokens", None)
                memory_operation_id = str(getattr(response, "memory_operation_id", "") or "").strip() or None
                retrieved_memories = getattr(response, "retrieved_memories", None) or []
                retrieved_files = getattr(response, "retrieved_files", None) or []
                retrieved_memories_count = len(retrieved_memories)
                retrieved_files_count = len(retrieved_files)

                if llm_provider and response_model_provider and response_model_provider.lower() != llm_provider.lower():
                    logger.warning(
                        "Backboard provider mismatch thread=%s requested=%s actual=%s",
                        thread_id,
                        llm_provider,
                        response_model_provider,
                    )
                elif llm_provider and not response_model_provider:
                    logger.warning(
                        "Backboard provider missing in response thread=%s requested=%s",
                        thread_id,
                        llm_provider,
                    )
                if model_name and response_model_name and response_model_name.lower() != model_name.lower():
                    logger.warning(
                        "Backboard model mismatch thread=%s requested=%s actual=%s",
                        thread_id,
                        model_name,
                        response_model_name,
                    )
                elif model_name and not response_model_name:
                    logger.warning(
                        "Backboard model missing in response thread=%s requested=%s",
                        thread_id,
                        model_name,
                    )

                logger.info(
                    "Backboard usage thread=%s provider=%s model=%s memory=%s memory_op=%s retrieved_files=%d retrieved_memories=%d tokens=%s/%s/%s",
                    thread_id,
                    response_model_provider or "(unknown)",
                    response_model_name or "(unknown)",
                    memory_mode,
                    memory_operation_id or "(none)",
                    retrieved_files_count,
                    retrieved_memories_count,
                    input_tokens if input_tokens is not None else "?",
                    output_tokens if output_tokens is not None else "?",
                    total_tokens if total_tokens is not None else "?",
                )

                return ChatResponse(
                    success=True,
                    response=response.content,
                    model_provider=response_model_provider,
                    model_name=response_model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    memory_operation_id=memory_operation_id,
                    retrieved_memories_count=retrieved_memories_count,
                    retrieved_files_count=retrieved_files_count,
                )
            except Exception as e:
                if self._is_indexing_in_progress_error(e) and max_wait_seconds > 0:
                    now = loop.time()
                    remaining = deadline - now
                    if remaining <= 0:
                        logger.error(
                            "Chat failed for thread %s: indexing wait timeout reached (%ds): %s",
                            thread_id,
                            max_wait_seconds,
                            e,
                        )
                        return ChatResponse(success=False, error=str(e))

                    sleep_for = min(retry_delay_seconds, remaining)
                    logger.info(
                        "Backboard documents still indexing for thread %s. Retrying chat in %.2fs (remaining %.2fs)",
                        thread_id,
                        sleep_for,
                        remaining,
                    )
                    await asyncio.sleep(sleep_for)
                    continue

                logger.error(f"Chat failed for thread {thread_id}: {e}")
                return ChatResponse(success=False, error=str(e))

    # ── Documents (RAG) ──

    def _get_document_path(self, assistant_id: str, document_type: str) -> str:
        docs_dir = settings.DOCUMENTS_PATH
        os.makedirs(docs_dir, exist_ok=True)
        safe_type = re.sub(r'[^\w\-]', '_', document_type)
        filename = f"{assistant_id}_{safe_type}.md"
        return os.path.join(docs_dir, filename)

    async def create_lore_document(
        self, assistant_id: str, document_type: str, content: str,
    ) -> DocumentCreated:
        if not self.is_available:
            return DocumentCreated(success=False)

        try:
            doc_path = self._get_document_path(assistant_id, document_type)
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(content)

            document = await self.client.upload_document_to_assistant(
                assistant_id=assistant_id,
                file_path=doc_path
            )
            logger.info(f"Created document: {document_type} -> {document.document_id}")
            return DocumentCreated(success=True, id=str(document.document_id))
        except Exception as e:
            logger.error(f"Failed to create document ({document_type}): {e}")
            return DocumentCreated(success=False)

    async def update_lore_document(
        self, assistant_id: str, document_id: str, document_type: str, content: str,
    ) -> DocumentUpdated:
        if not self.is_available:
            return DocumentUpdated(success=False)

        try:
            doc_path = self._get_document_path(assistant_id, document_type)
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(content)

            await self.client.delete_document(document_id=document_id)
            logger.debug(f"Deleted existing document: {document_type} ({document_id})")

            document = await self.client.upload_document_to_assistant(
                assistant_id=assistant_id,
                file_path=doc_path
            )
            logger.info(f"Updated document: {document_type} -> {document.document_id}")
            return DocumentUpdated(success=True, id=str(document.document_id))
        except Exception as e:
            logger.error(f"Failed to update document ({document_type}): {e}")
            return DocumentUpdated(success=False)
