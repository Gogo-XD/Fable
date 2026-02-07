"""Relation domain model."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

from app.models.enums import EntitySource


class RelationCreate(BaseModel):
    """Payload for manually creating a relation."""
    source_entity_id: str
    target_entity_id: str
    type: str
    context: Optional[str] = None
    weight: float = Field(default=0.5, ge=0.0, le=1.0)


class RelationUpdate(BaseModel):
    """Payload for updating a relation."""
    type: Optional[str] = None
    context: Optional[str] = None
    weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class Relation(BaseModel):
    """A directed edge between two entities in the world graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    source_entity_id: str
    target_entity_id: str
    type: str
    context: Optional[str] = None
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    source: EntitySource = EntitySource.USER
    source_note_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
