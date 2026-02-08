"""Entity domain model."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

from app.models.enums import EntitySource


class EntityCreate(BaseModel):
    """Payload for manually creating an entity."""
    name: str
    type: str
    subtype: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    context: Optional[str] = None
    summary: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    status: str = "active"


class EntityUpdate(BaseModel):
    """Payload for updating an entity. All fields optional — only provided fields are patched."""
    name: Optional[str] = None
    type: Optional[str] = None
    subtype: Optional[str] = None
    aliases: Optional[list[str]] = None
    context: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    image_url: Optional[str] = None
    status: Optional[str] = None


class Entity(BaseModel):
    """An entity node in the world graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    name: str
    type: str
    subtype: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    context: Optional[str] = None
    summary: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    status: str = "active"
    exists_at_marker: bool = True
    source: EntitySource = EntitySource.USER
    source_note_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
