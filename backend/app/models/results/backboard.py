"""
Result models for Backboard service operations.
"""

from pydantic import BaseModel
from typing import Optional

class BackboardResult(BaseModel):
    """Base result for Backboard operations."""
    success: bool

class AssistantCreated(BackboardResult):
    """Result of creating an assistant."""
    id: Optional[str] = None


class ThreadCreated(BackboardResult):
    """Result of creating a conversation thread."""
    id: Optional[str] = None


class ThreadDeleted(BackboardResult):
    """Result of deleting a conversation thread."""
    pass


class DocumentCreated(BackboardResult):
    """Result of creating a document."""
    id: Optional[str] = None


class DocumentUpdated(BackboardResult):
    """Result of updating a document."""
    id: Optional[str] = None


class ChatResponse(BackboardResult):
    """Result of a chat message exchange."""
    response: Optional[str] = None
