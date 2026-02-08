"""Timeline API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import TimelineServiceDep, WorldRagSyncServiceDep
from app.models import (
    TimelineMarker,
    TimelineMarkerCreate,
    TimelineMarkerReposition,
    TimelineRebuildResult,
    TimelineMarkerUpdate,
    TimelineOperation,
    TimelineOperationCreate,
    TimelineOperationUpdate,
    TimelineSnapshot,
    TimelineSnapshotUpsert,
    TimelineWorldState,
)

router = APIRouter()


@router.get("/{world_id}/markers", response_model=list[TimelineMarker])
async def list_markers(
    world_id: str,
    service: TimelineServiceDep,
    include_operations: bool = Query(default=False),
):
    return await service.list_markers(world_id, include_operations=include_operations)


@router.post("/{world_id}/markers", response_model=TimelineMarker, status_code=201)
async def create_marker(
    world_id: str,
    body: TimelineMarkerCreate,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        marker = await service.create_marker(world_id, body)
        await rag_sync.mark_dirty(world_id, reason="timeline_marker_create")
        return marker
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{world_id}/markers/{marker_id}", response_model=TimelineMarker)
async def get_marker(
    world_id: str,
    marker_id: str,
    service: TimelineServiceDep,
    include_operations: bool = Query(default=True),
):
    marker = await service.get_marker(world_id, marker_id, include_operations=include_operations)
    if not marker:
        raise HTTPException(404, "Timeline marker not found")
    return marker


@router.put("/{world_id}/markers/{marker_id}", response_model=TimelineMarker)
async def update_marker(
    world_id: str,
    marker_id: str,
    body: TimelineMarkerUpdate,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        marker = await service.update_marker(world_id, marker_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not marker:
        raise HTTPException(404, "Timeline marker not found")
    await rag_sync.mark_dirty(world_id, reason="timeline_marker_update")
    return marker


@router.post("/{world_id}/markers/{marker_id}/reposition", response_model=TimelineMarker)
async def reposition_marker(
    world_id: str,
    marker_id: str,
    body: TimelineMarkerReposition,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        marker = await service.reposition_marker(world_id, marker_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not marker:
        raise HTTPException(404, "Timeline marker not found")
    await rag_sync.mark_dirty(world_id, reason="timeline_marker_reposition")
    return marker


@router.delete("/{world_id}/markers/{marker_id}")
async def delete_marker(
    world_id: str,
    marker_id: str,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    deleted = await service.delete_marker(world_id, marker_id)
    if not deleted:
        raise HTTPException(404, "Timeline marker not found")
    await rag_sync.mark_dirty(world_id, reason="timeline_marker_delete")
    return {"status": "deleted", "marker_id": marker_id}


@router.get("/{world_id}/markers/{marker_id}/operations", response_model=list[TimelineOperation])
async def list_operations(world_id: str, marker_id: str, service: TimelineServiceDep):
    return await service.list_operations(world_id, marker_id)


@router.post(
    "/{world_id}/markers/{marker_id}/operations",
    response_model=TimelineOperation,
    status_code=201,
)
async def create_operation(
    world_id: str,
    marker_id: str,
    body: TimelineOperationCreate,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        operation = await service.create_operation(world_id, marker_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not operation:
        raise HTTPException(404, "Timeline marker not found")
    await rag_sync.mark_dirty(world_id, reason="timeline_operation_create")
    return operation


@router.put(
    "/{world_id}/markers/{marker_id}/operations/{operation_id}",
    response_model=TimelineOperation,
)
async def update_operation(
    world_id: str,
    marker_id: str,
    operation_id: str,
    body: TimelineOperationUpdate,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        operation = await service.update_operation(world_id, marker_id, operation_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not operation:
        raise HTTPException(404, "Timeline operation not found")
    await rag_sync.mark_dirty(world_id, reason="timeline_operation_update")
    return operation


@router.delete("/{world_id}/markers/{marker_id}/operations/{operation_id}")
async def delete_operation(
    world_id: str,
    marker_id: str,
    operation_id: str,
    service: TimelineServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    deleted = await service.delete_operation(world_id, marker_id, operation_id)
    if not deleted:
        raise HTTPException(404, "Timeline operation not found")
    await rag_sync.mark_dirty(world_id, reason="timeline_operation_delete")
    return {"status": "deleted", "operation_id": operation_id}


@router.post("/{world_id}/rebuild", response_model=TimelineRebuildResult)
async def rebuild_timeline(world_id: str, service: TimelineServiceDep):
    return await service.rebuild_snapshots(world_id)


@router.get("/{world_id}/state", response_model=TimelineWorldState)
async def get_world_state(
    world_id: str,
    service: TimelineServiceDep,
    marker_id: Optional[str] = Query(default=None),
):
    try:
        return await service.get_world_state(world_id=world_id, marker_id=marker_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{world_id}/snapshots", response_model=list[TimelineSnapshot])
async def list_snapshots(world_id: str, service: TimelineServiceDep):
    return await service.list_snapshots(world_id)


@router.get("/{world_id}/snapshots/{marker_id}", response_model=TimelineSnapshot)
async def get_snapshot(world_id: str, marker_id: str, service: TimelineServiceDep):
    snapshot = await service.get_snapshot(world_id, marker_id)
    if not snapshot:
        raise HTTPException(404, "Timeline snapshot not found")
    return snapshot


@router.put("/{world_id}/snapshots/{marker_id}", response_model=TimelineSnapshot)
async def upsert_snapshot(
    world_id: str,
    marker_id: str,
    body: TimelineSnapshotUpsert,
    service: TimelineServiceDep,
):
    return await service.upsert_snapshot(world_id, marker_id, body)


@router.post("/{world_id}/snapshots/{marker_id}/generate", response_model=TimelineSnapshot)
async def generate_snapshot(world_id: str, marker_id: str, service: TimelineServiceDep):
    try:
        return await service.generate_snapshot(world_id, marker_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
