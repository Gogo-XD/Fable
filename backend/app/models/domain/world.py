"""World domain model."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4


class WorldCreate(BaseModel):
    """Payload for creating a new world."""
    name: str
    description: Optional[str] = None
    entity_types: list[str] = Field(
        default_factory=lambda: ["character", "location", "event", "item", "organization", "concept"]
    )
    relation_types: list[str] = Field(
        default_factory=lambda: ["ally_of", "enemy_of", "parent_of", "child_of", "located_in", "participated_in", "member_of"]
    )


class WorldUpdate(BaseModel):
    """Payload for updating a world."""
    name: Optional[str] = None
    description: Optional[str] = None
    entity_types: Optional[list[str]] = None
    relation_types: Optional[list[str]] = None


class World(BaseModel):
    """A world — the top-level container for an entire knowledge graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    assistant_id: Optional[str] = None
    entity_types: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
