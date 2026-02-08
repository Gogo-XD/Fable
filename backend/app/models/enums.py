"""
Enum definitions for the Fable API.

EntityType and RelationType are dynamic (str) to allow world-specific types.
"""
from enum import Enum


class EntitySource(str, Enum):
    """Who created/owns an entity or relation."""
    USER = "user"
    AI = "ai"


class NoteStatus(str, Enum):
    """Lifecycle status of a note."""
    DRAFT = "draft"
    SAVED = "saved"
    ANALYZED = "analyzed"


class EntityResolutionStatus(str, Enum):
    """Resolution status for entities detected during analysis."""
    USER = "user"
    AI = "ai"
    PENDING = "pending"


def normalize_type(type_str: str) -> str:
    """
    Normalize a type string for consistency.

    - Lowercase
    - Strip whitespace
    - Replace spaces with underscores

    Examples:
        "Character" -> "character"
        "Parent Of" -> "parent_of"
        " sponsored by " -> "sponsored_by"
    """
    return type_str.lower().strip().replace(" ", "_")
