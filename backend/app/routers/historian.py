"""Historian NPC routes."""

from fastapi import APIRouter, HTTPException

from app.dependencies import HistorianServiceDep
from app.models import HistorianMessageRequest, HistorianMessageResponse

router = APIRouter()


@router.post("/{world_id}/message", response_model=HistorianMessageResponse)
async def message_historian(
    world_id: str,
    body: HistorianMessageRequest,
    service: HistorianServiceDep,
):
    try:
        return await service.send_message(
            world_id=world_id,
            message=body.message,
            thread_id=body.thread_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

