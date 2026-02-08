"""World management endpoints."""

from fastapi import APIRouter, HTTPException

from app.models import World, WorldCreate, WorldUpdate, RagCompileRequest, RagCompileResult
from app.dependencies import WorldServiceDep, WorldRagSyncServiceDep

router = APIRouter()


@router.get("/", response_model=list[World])
async def list_worlds(service: WorldServiceDep):
    return await service.list_worlds()


@router.post("/", response_model=World, status_code=201)
async def create_world(body: WorldCreate, service: WorldServiceDep):
    return await service.create_world(body)


@router.get("/{world_id}", response_model=World)
async def get_world(world_id: str, service: WorldServiceDep):
    world = await service.get_world(world_id)
    if not world:
        raise HTTPException(404, "World not found")
    return world


@router.put("/{world_id}", response_model=World)
async def update_world(
    world_id: str,
    body: WorldUpdate,
    service: WorldServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    world = await service.update_world(world_id, body)
    if not world:
        raise HTTPException(404, "World not found")
    if body.description is not None or body.entity_types is not None or body.relation_types is not None:
        await rag_sync.mark_dirty(world_id, reason="world_update")
    return world


@router.delete("/{world_id}")
async def delete_world(world_id: str, service: WorldServiceDep):
    deleted = await service.delete_world(world_id)
    if not deleted:
        raise HTTPException(404, "World not found")
    return {"status": "deleted", "world_id": world_id}


@router.post("/{world_id}/rag/compile", response_model=RagCompileResult)
async def compile_world_rag(
    world_id: str,
    body: RagCompileRequest,
    service: WorldRagSyncServiceDep,
):
    try:
        return await service.compile_world_documents(world_id=world_id, data=body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
