"""Note domain model."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

from app.models.enums import NoteStatus


class NoteCreate(BaseModel):
    """Payload for creating a note."""
    title: Optional[str] = None
    content: str


class NoteUpdate(BaseModel):
    """Payload for updating a note."""
    title: Optional[str] = None
    content: Optional[str] = None


class Note(BaseModel):
    """A freeform text note — the primary input method for worldbuilding."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    title: Optional[str] = None
    content: str
    status: NoteStatus = NoteStatus.DRAFT
    analysis_thread_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
