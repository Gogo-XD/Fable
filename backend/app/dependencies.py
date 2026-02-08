"""
Dependency injection for FastAPI routes.

Provides typed service dependencies that enable IDE navigation (Ctrl+Click).
"""

from typing import Annotated
from fastapi import Request, Depends

from app.services.backboard import BackboardService
from app.services.canon_guardian import CanonGuardianService
from app.services.canon_mechanic import CanonMechanicService
from app.services.graph import GraphService
from app.services.historian import HistorianService
from app.services.lore import LoreService
from app.services.timeline import TimelineService
from app.services.world import WorldService
from app.services.world_rag_compiler import WorldRagCompilerService
from app.services.world_rag_sync import WorldRagSyncService


def get_backboard_service(request: Request) -> BackboardService:
    return request.app.state.backboard


def get_lore_service(request: Request) -> LoreService:
    return request.app.state.lore_service


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_world_service(request: Request) -> WorldService:
    return request.app.state.world_service


def get_timeline_service(request: Request) -> TimelineService:
    return request.app.state.timeline_service


def get_canon_guardian_service(request: Request) -> CanonGuardianService:
    return request.app.state.canon_guardian_service


def get_canon_mechanic_service(request: Request) -> CanonMechanicService:
    return request.app.state.canon_mechanic_service


def get_world_rag_compiler_service(request: Request) -> WorldRagCompilerService:
    return request.app.state.world_rag_compiler_service


def get_world_rag_sync_service(request: Request) -> WorldRagSyncService:
    return request.app.state.world_rag_sync_service


def get_historian_service(request: Request) -> HistorianService:
    return request.app.state.historian_service


BackboardServiceDep = Annotated[BackboardService, Depends(get_backboard_service)]
LoreServiceDep = Annotated[LoreService, Depends(get_lore_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
WorldServiceDep = Annotated[WorldService, Depends(get_world_service)]
TimelineServiceDep = Annotated[TimelineService, Depends(get_timeline_service)]
CanonGuardianServiceDep = Annotated[CanonGuardianService, Depends(get_canon_guardian_service)]
CanonMechanicServiceDep = Annotated[CanonMechanicService, Depends(get_canon_mechanic_service)]
WorldRagCompilerServiceDep = Annotated[WorldRagCompilerService, Depends(get_world_rag_compiler_service)]
WorldRagSyncServiceDep = Annotated[WorldRagSyncService, Depends(get_world_rag_sync_service)]
HistorianServiceDep = Annotated[HistorianService, Depends(get_historian_service)]
