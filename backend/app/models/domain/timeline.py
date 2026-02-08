"""Timeline domain models."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.domain.entity import Entity
from app.models.domain.relation import Relation
from app.models.enums import EntitySource


class TimelineOperationCreate(BaseModel):
    """Payload for creating a timeline operation."""

    op_type: str
    target_kind: str = Field(
        description="The projection target kind: entity, relation, or world.",
    )
    target_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    order_index: int = Field(default=0, ge=0)


class TimelineOperationUpdate(BaseModel):
    """Payload for updating a timeline operation."""

    op_type: Optional[str] = None
    target_kind: Optional[str] = None
    target_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    order_index: Optional[int] = Field(default=None, ge=0)


class TimelineOperation(BaseModel):
    """A single operation attached to a timeline marker."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    marker_id: str
    op_type: str
    target_kind: str
    target_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    order_index: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TimelineMarkerCreate(BaseModel):
    """Payload for creating a timeline marker."""

    title: str
    summary: Optional[str] = None
    marker_kind: str = Field(
        default="explicit",
        description="explicit or semantic",
    )
    placement_status: str = Field(
        default="placed",
        description="placed or unplaced",
    )
    date_label: Optional[str] = Field(
        default=None,
        description='Display date label, e.g. "1205" or "During the Great Cataclysm".',
    )
    date_sort_value: Optional[float] = Field(
        default=None,
        description="Numeric chronology used for sorting explicit markers.",
    )
    sort_key: Optional[float] = Field(
        default=None,
        description="Manual sortable key. If omitted, service computes one.",
    )
    source: EntitySource = EntitySource.USER
    source_note_id: Optional[str] = None
    operations: list[TimelineOperationCreate] = Field(default_factory=list)


class TimelineMarkerUpdate(BaseModel):
    """Payload for updating a timeline marker."""

    title: Optional[str] = None
    summary: Optional[str] = None
    marker_kind: Optional[str] = None
    placement_status: Optional[str] = None
    date_label: Optional[str] = None
    date_sort_value: Optional[float] = None
    sort_key: Optional[float] = None
    source_note_id: Optional[str] = None


class TimelineMarkerReposition(BaseModel):
    """Payload for changing marker ordering."""

    sort_key: float
    placement_status: str = "placed"


class TimelineMarker(BaseModel):
    """A timeline marker describing a point-in-time world change set."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    title: str
    summary: Optional[str] = None
    marker_kind: str = "explicit"
    placement_status: str = "placed"
    date_label: Optional[str] = None
    date_sort_value: Optional[float] = None
    sort_key: float
    source: EntitySource = EntitySource.USER
    source_note_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operations: list[TimelineOperation] = Field(default_factory=list)


class TimelineSnapshotUpsert(BaseModel):
    """Payload for storing a timeline snapshot."""

    state_json: dict[str, Any]
    state_hash: Optional[str] = None
    applied_marker_count: int = 0
    entity_count: int = 0
    relation_count: int = 0


class TimelineSnapshot(BaseModel):
    """Cached world projection state at a marker."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    world_id: str
    marker_id: str
    state_json: dict[str, Any] = Field(default_factory=dict)
    state_hash: Optional[str] = None
    applied_marker_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TimelineWorldState(BaseModel):
    """Projected world state at a timeline point."""

    world_id: str
    marker_id: Optional[str] = None
    applied_marker_count: int = 0
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    from_snapshot_marker_id: Optional[str] = None
    note: Optional[str] = None


class TimelineRebuildResult(BaseModel):
    """Summary of a timeline snapshot rebuild run."""

    status: str = "rebuilt"
    world_id: str
    marker_count: int = 0
    snapshot_count: int = 0
    rebuilt_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
