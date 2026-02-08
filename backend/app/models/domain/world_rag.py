"""Domain models for world RAG document compilation."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


RagSlotSyncStatus = Literal["created", "updated", "unchanged", "skipped", "failed", "dry_run"]


class RagCompileRequest(BaseModel):
    """Request payload for compiling world data into RAG document slots."""

    dry_run: bool = False
    force_upload: bool = False
    include_empty_slots: bool = True
    max_doc_chars: int = Field(default=60000, ge=5000, le=250000)
    max_note_excerpt_chars: int = Field(default=1200, ge=200, le=8000)
    max_operation_payload_chars: int = Field(default=280, ge=80, le=5000)


class RagDocumentSyncStatusResult(BaseModel):
    """Per-slot sync result for a RAG compile run."""

    slot_key: str
    slot_title: str
    sync_status: RagSlotSyncStatus
    document_id: Optional[str] = None
    content_hash: str
    content_size: int = 0
    record_count: int = 0
    error: Optional[str] = None


class RagCompileResult(BaseModel):
    """Top-level result for a world RAG compile run."""

    status: str
    world_id: str
    assistant_id: Optional[str] = None
    total_slots: int = 0
    processed_slots: int = 0
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    slots: list[RagDocumentSyncStatusResult] = Field(default_factory=list)
    message: Optional[str] = None
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

