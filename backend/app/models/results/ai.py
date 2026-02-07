"""Result models for AI extraction operations."""

from pydantic import BaseModel
from typing import Optional

from app.models.results.backboard import BackboardResult


class EntityExtraction(BaseModel):
    """A single entity extracted from a note by the LLM."""
    name: str
    type: str
    subtype: Optional[str] = None
    aliases: list[str] = []
    summary: Optional[str] = None
    context: Optional[str] = None
    tags: list[str] = []


class RelationExtraction(BaseModel):
    """A single relation extracted from a note by the LLM."""
    source_name: str
    target_name: str
    type: str
    context: Optional[str] = None


class NoteAnalysisResult(BackboardResult):
    """Full result of analyzing a note — lists of extracted entities and relations."""
    entities: list[EntityExtraction] = []
    relations: list[RelationExtraction] = []
