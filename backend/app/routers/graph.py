"""Graph API routes."""

from fastapi import APIRouter, Query

from app.dependencies import GraphServiceDep

router = APIRouter()


@router.get("/{world_id}")
async def get_graph(
    world_id: str,
    service: GraphServiceDep,
    entity_type: list[str] | None = Query(default=None),
    relation_type: list[str] | None = Query(default=None),
    focus_entity_id: str | None = Query(default=None),
):
    return await service.get_graph(
        world_id=world_id,
        entity_types=entity_type,
        relation_types=relation_type,
        focus_entity_id=focus_entity_id,
    )
