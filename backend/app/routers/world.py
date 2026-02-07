"""World management endpoints."""

from fastapi import APIRouter, HTTPException

from app.models import World, WorldCreate, WorldUpdate
from app.dependencies import WorldServiceDep

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
async def update_world(world_id: str, body: WorldUpdate, service: WorldServiceDep):
    world = await service.update_world(world_id, body)
    if not world:
        raise HTTPException(404, "World not found")
    return world


@router.delete("/{world_id}")
async def delete_world(world_id: str, service: WorldServiceDep):
    deleted = await service.delete_world(world_id)
    if not deleted:
        raise HTTPException(404, "World not found")
    return {"status": "deleted", "world_id": world_id}
