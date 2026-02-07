"""
Dependency injection for FastAPI routes.

Provides typed service dependencies that enable IDE navigation (Ctrl+Click).
"""

from typing import Annotated
from fastapi import Request, Depends

from app.services.backboard import BackboardService
from app.services.graph import GraphService
from app.services.lore import LoreService
from app.services.world import WorldService


def get_backboard_service(request: Request) -> BackboardService:
    return request.app.state.backboard


def get_lore_service(request: Request) -> LoreService:
    return request.app.state.lore_service


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_world_service(request: Request) -> WorldService:
    return request.app.state.world_service


BackboardServiceDep = Annotated[BackboardService, Depends(get_backboard_service)]
LoreServiceDep = Annotated[LoreService, Depends(get_lore_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
WorldServiceDep = Annotated[WorldService, Depends(get_world_service)]
