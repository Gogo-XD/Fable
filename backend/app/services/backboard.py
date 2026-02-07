"""
Backboard.io integration service.

Handles assistant management, thread lifecycle, document storage, and chat.
Analysis/extraction logic lives in LoreService — this is the transport layer.
"""

import os
import re

from backboard import BackboardClient

from app.config import settings
from app.logging import get_logger
from app.models import (
    AssistantCreated, ThreadCreated, ThreadDeleted,
    DocumentCreated, DocumentUpdated, ChatResponse,
)
from app.services.prompts import build_world_assistant_prompt

logger = get_logger('services.backboard')

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
            thread = await self.client.create_thread(assistant_id=assistant_id)
            return ThreadCreated(success=True, id=str(thread.thread_id))
        except Exception as e:
            logger.error(f"Failed to create thread: {e}")
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

    async def chat(self, thread_id: str, prompt: str) -> ChatResponse:
        if not self.is_available:
            return ChatResponse(success=False)

        try:
            response = await self.client.add_message(
                thread_id=thread_id,
                content=prompt
            )
            return ChatResponse(success=True, response=response.content)
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return ChatResponse(success=False)

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
