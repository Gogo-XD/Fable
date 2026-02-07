"""Result models for service operations."""

from app.models.results.backboard import (
    BackboardResult, AssistantCreated, ThreadCreated, ThreadDeleted,
    DocumentCreated, DocumentUpdated, ChatResponse,
)
from app.models.results.ai import EntityExtraction, RelationExtraction, NoteAnalysisResult

__all__ = [
    "BackboardResult", "AssistantCreated", "ThreadCreated", "ThreadDeleted",
    "DocumentCreated", "DocumentUpdated", "ChatResponse",
    "EntityExtraction", "RelationExtraction", "NoteAnalysisResult",
]
