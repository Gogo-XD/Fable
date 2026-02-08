"""Relation routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import LoreServiceDep, WorldRagSyncServiceDep
from app.models import Relation, RelationCreate, RelationUpdate

router = APIRouter()


@router.post("/{world_id}/relations", response_model=Relation, status_code=201)
async def create_relation(
    world_id: str,
    body: RelationCreate,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    relation = await service.create_relation(world_id, body)
    await rag_sync.mark_dirty(world_id, reason="relation_create")
    return relation


@router.get("/{world_id}/relations", response_model=list[Relation])
async def list_relations(
    world_id: str,
    service: LoreServiceDep,
    entity_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
):
    return await service.list_relations(world_id, entity_id=entity_id, type=type)


@router.get("/{world_id}/relations/{relation_id}", response_model=Relation)
async def get_relation(world_id: str, relation_id: str, service: LoreServiceDep):
    relation = await service.get_relation(world_id, relation_id)
    if not relation:
        raise HTTPException(404, "Relation not found")
    return relation


@router.put("/{world_id}/relations/{relation_id}", response_model=Relation)
async def update_relation(
    world_id: str,
    relation_id: str,
    body: RelationUpdate,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    relation = await service.update_relation(world_id, relation_id, body)
    if not relation:
        raise HTTPException(404, "Relation not found")
    await rag_sync.mark_dirty(world_id, reason="relation_update")
    return relation


@router.delete("/{world_id}/relations/{relation_id}")
async def delete_relation(
    world_id: str,
    relation_id: str,
    service: LoreServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    deleted = await service.delete_relation(world_id, relation_id)
    if not deleted:
        raise HTTPException(404, "Relation not found")
    await rag_sync.mark_dirty(world_id, reason="relation_delete")
    return {"status": "deleted", "id": relation_id}
