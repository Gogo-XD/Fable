"""Canon Guardian API routes."""

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import CanonGuardianServiceDep, CanonMechanicServiceDep, WorldRagSyncServiceDep
from app.models import (
    GuardianApplyRequest,
    GuardianApplyResult,
    GuardianFindingStatusUpdate,
    GuardianRunDetail,
    GuardianScanAccepted,
    GuardianScanRequest,
    MechanicAcceptRequest,
    MechanicAcceptResult,
    MechanicGenerateAccepted,
    MechanicGenerateRequest,
    MechanicRunDetail,
)

router = APIRouter()


@router.post("/{world_id}/scan", response_model=GuardianScanAccepted, status_code=202)
async def scan_world(
    world_id: str,
    body: GuardianScanRequest,
    service: CanonGuardianServiceDep,
):
    try:
        return await service.create_world_scan_run(world_id=world_id, data=body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{world_id}/runs/{run_id}", response_model=GuardianRunDetail)
async def get_run(
    world_id: str,
    run_id: str,
    service: CanonGuardianServiceDep,
    include_details: bool = Query(default=True),
):
    run = await service.get_run(world_id=world_id, run_id=run_id, include_details=include_details)
    if not run:
        raise HTTPException(404, "Guardian run not found")
    return run


@router.post("/{world_id}/runs/{run_id}/apply", response_model=GuardianApplyResult)
async def apply_run_actions(
    world_id: str,
    run_id: str,
    body: GuardianApplyRequest,
    service: CanonGuardianServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        result = await service.apply_actions(world_id=world_id, run_id=run_id, data=body)
        if result.applied_actions > 0:
            await rag_sync.mark_dirty(world_id, reason="guardian_apply_actions")
        return result
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post(
    "/{world_id}/runs/{run_id}/findings/{finding_id}/dismiss",
    response_model=GuardianFindingStatusUpdate,
)
async def dismiss_run_finding(
    world_id: str,
    run_id: str,
    finding_id: str,
    service: CanonGuardianServiceDep,
):
    try:
        return await service.dismiss_finding(world_id=world_id, run_id=run_id, finding_id=finding_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post(
    "/{world_id}/runs/{run_id}/mechanic/generate",
    response_model=MechanicGenerateAccepted,
    status_code=202,
)
async def generate_mechanic_options(
    world_id: str,
    run_id: str,
    body: MechanicGenerateRequest,
    service: CanonMechanicServiceDep,
):
    try:
        return await service.create_mechanic_run(world_id=world_id, run_id=run_id, data=body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{world_id}/mechanic/{mechanic_run_id}", response_model=MechanicRunDetail)
async def get_mechanic_run(
    world_id: str,
    mechanic_run_id: str,
    service: CanonMechanicServiceDep,
    include_options: bool = Query(default=True),
):
    run = await service.get_mechanic_run(
        world_id=world_id,
        mechanic_run_id=mechanic_run_id,
        include_options=include_options,
    )
    if not run:
        raise HTTPException(404, "Mechanic run not found")
    return run


@router.post("/{world_id}/mechanic/{mechanic_run_id}/accept", response_model=MechanicAcceptResult)
async def accept_mechanic_options(
    world_id: str,
    mechanic_run_id: str,
    body: MechanicAcceptRequest,
    service: CanonMechanicServiceDep,
    rag_sync: WorldRagSyncServiceDep,
):
    try:
        result = await service.accept_options(world_id=world_id, mechanic_run_id=mechanic_run_id, data=body)
        if int(result.applied_options) > 0:
            await rag_sync.mark_dirty(world_id, reason="mechanic_option_apply")
        return result
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
