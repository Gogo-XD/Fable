"""Entity routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import LoreServiceDep
from app.models import Entity, EntityCreate, EntityUpdate

router = APIRouter()


@router.post("/{world_id}/entities", response_model=Entity, status_code=201)
async def create_entity(world_id: str, body: EntityCreate, service: LoreServiceDep):
    return await service.create_entity(world_id, body)


@router.get("/{world_id}/entities", response_model=list[Entity])
async def list_entities(
    world_id: str,
    service: LoreServiceDep,
    type: Optional[str] = Query(None),
    subtype: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    return await service.list_entities(world_id, type=type, subtype=subtype, tag=tag, search=search)


@router.get("/{world_id}/entities/{entity_id}", response_model=Entity)
async def get_entity(world_id: str, entity_id: str, service: LoreServiceDep):
    entity = await service.get_entity(world_id, entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    return entity


@router.put("/{world_id}/entities/{entity_id}", response_model=Entity)
async def update_entity(world_id: str, entity_id: str, body: EntityUpdate, service: LoreServiceDep):
    entity = await service.update_entity(world_id, entity_id, body)
    if not entity:
        raise HTTPException(404, "Entity not found")
    return entity


@router.delete("/{world_id}/entities/{entity_id}")
async def delete_entity(world_id: str, entity_id: str, service: LoreServiceDep):
    deleted = await service.delete_entity(world_id, entity_id)
    if not deleted:
        raise HTTPException(404, "Entity not found")
    return {"status": "deleted", "id": entity_id}

