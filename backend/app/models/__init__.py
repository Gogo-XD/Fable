"""
Worldbuilding Companion models.

Usage:
    from app.models import Entity, EntityCreate, World, Relation, Note
    from app.models import EntitySource, NoteStatus, normalize_type
    from app.models import NoteAnalysisResult, EntityExtraction, RelationExtraction
"""

# --- Enums & utilities ---
from app.models.enums import (
    EntitySource,
    NoteStatus,
    EntityResolutionStatus,
    normalize_type,
)

# --- Domain models ---
from app.models.domain import (
    World, WorldCreate, WorldUpdate,
    Entity, EntityCreate, EntityUpdate,
    Relation, RelationCreate, RelationUpdate,
    Note, NoteCreate, NoteUpdate,
)

# --- Result models ---
from app.models.results import (
    BackboardResult,
    AssistantCreated, ThreadCreated, ThreadDeleted,
    DocumentCreated, DocumentUpdated, ChatResponse,
    EntityExtraction, RelationExtraction, NoteAnalysisResult,
)

__all__ = [
    # Enums
    "EntitySource", "NoteStatus", "EntityResolutionStatus", "normalize_type",
    # Domain
    "World", "WorldCreate", "WorldUpdate",
    "Entity", "EntityCreate", "EntityUpdate",
    "Relation", "RelationCreate", "RelationUpdate",
    "Note", "NoteCreate", "NoteUpdate",
    # Results
    "BackboardResult",
    "AssistantCreated", "ThreadCreated", "ThreadDeleted",
    "DocumentCreated", "DocumentUpdated", "ChatResponse",
    "EntityExtraction", "RelationExtraction", "NoteAnalysisResult",
]
