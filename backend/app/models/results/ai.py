"""Result models for AI extraction operations."""

from pydantic import BaseModel, Field
from typing import Any, Optional

from app.models.results.backboard import BackboardResult


class EntityExtraction(BaseModel):
    """A single entity extracted from a note by the LLM."""

    name: str
    type: str
    subtype: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    context: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class RelationExtraction(BaseModel):
    """A single relation extracted from a note by the LLM."""

    source_name: str
    target_name: str
    type: str
    context: Optional[str] = None


class TimelineMarkerChangeExtraction(BaseModel):
    """A single world-state change associated with a timeline marker."""

    op_type: str
    target_kind: str
    target_name: Optional[str] = None
    source_name: Optional[str] = None
    relation_type: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TimelineMarkerExtraction(BaseModel):
    """A timeline marker extracted from a note by the LLM."""

    title: str
    summary: Optional[str] = None
    marker_kind: str = "semantic"
    date_label: Optional[str] = None
    date_sort_value: Optional[float] = None
    changes: list[TimelineMarkerChangeExtraction] = Field(default_factory=list)


class NoteAnalysisResult(BackboardResult):
    """Full result of analyzing a note with entities, relations, and timeline markers."""

    entities: list[EntityExtraction] = Field(default_factory=list)
    relations: list[RelationExtraction] = Field(default_factory=list)
    timeline_markers: list[TimelineMarkerExtraction] = Field(default_factory=list)
