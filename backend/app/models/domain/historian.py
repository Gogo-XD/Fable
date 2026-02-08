"""Domain models for Historian NPC chat workflows."""

from pydantic import BaseModel, Field
from typing import Optional


class HistorianMessageRequest(BaseModel):
    """Request payload for sending a message to the Historian NPC."""

    message: str = Field(min_length=1, max_length=12000)
    thread_id: Optional[str] = None


class HistorianMessageResponse(BaseModel):
    """Response payload for a Historian NPC message exchange."""

    thread_id: str
    response: str
    rag_refreshed: bool = False
    rag_compile_status: Optional[str] = None
    rag_compile_error: Optional[str] = None

