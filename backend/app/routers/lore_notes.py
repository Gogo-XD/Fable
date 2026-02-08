"""Note routes."""

from fastapi import APIRouter, HTTPException

from app.dependencies import LoreServiceDep, WorldRagSyncServiceDep
from app.models import Note, NoteCreate, NoteUpdate

router = APIRouter()


@router.post("/{world_id}/notes", response_model=Note, status_code=201)
async def create_note(
    world_id: str,
    body: NoteCreate,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    note = await service.create_note(world_id, body)
    await rag_sync.mark_dirty(world_id, reason="note_create")
    return note


@router.get("/{world_id}/notes", response_model=list[Note])
async def list_notes(world_id: str, service: LoreServiceDep):
    return await service.list_notes(world_id)


@router.get("/{world_id}/notes/{note_id}", response_model=Note)
async def get_note(world_id: str, note_id: str, service: LoreServiceDep):
    note = await service.get_note(world_id, note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    return note


@router.put("/{world_id}/notes/{note_id}", response_model=Note)
async def update_note(
    world_id: str,
    note_id: str,
    body: NoteUpdate,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    note = await service.update_note(world_id, note_id, body)
    if not note:
        raise HTTPException(404, "Note not found")
    await rag_sync.mark_dirty(world_id, reason="note_update")
    return note


@router.delete("/{world_id}/notes/{note_id}")
async def delete_note(
    world_id: str,
    note_id: str,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    deleted = await service.delete_note(world_id, note_id)
    if not deleted:
        raise HTTPException(404, "Note not found")
    await rag_sync.mark_dirty(world_id, reason="note_delete")
    return {"status": "deleted", "id": note_id}


@router.post("/{world_id}/notes/{note_id}/analyze")
async def analyze_note(
    world_id: str,
    note_id: str,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        result = await service.analyze_note(world_id, note_id)
        await rag_sync.mark_dirty(world_id, reason="note_analyze")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{world_id}/notes/analyze-all")
async def analyze_all_notes(
    world_id: str,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        result = await service.analyze_all_unanalyzed_notes(world_id)
        if int(result.get("notes_analyzed", 0)) > 0:
            await rag_sync.mark_dirty(world_id, reason="notes_analyze_all")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
