"""
Fable - FastAPI Backend
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.config import settings
from app.database.db import init_db
from app.logging import setup_logging, get_logger
from app.routers import (
    canon_guardian,
    graph,
    historian,
    lore_entities,
    lore_notes,
    lore_relations,
    timeline,
    world,
)
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

logger = get_logger('main')

# Socket.IO server for real-time graph updates
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting Fable API")

    await init_db()
    logger.info("Database initialized")

    # Initialize services
    backboard = BackboardService()
    await backboard.initialize()
    app.state.backboard = backboard

    app.state.world_service = WorldService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
    )
    app.state.timeline_service = TimelineService(
        db_path=settings.DATABASE_PATH,
    )
    app.state.lore_service = LoreService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
        timeline_service=app.state.timeline_service,
    )
    app.state.graph_service = GraphService(
        db_path=settings.DATABASE_PATH,
    )
    app.state.canon_guardian_service = CanonGuardianService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
    )
    app.state.canon_mechanic_service = CanonMechanicService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
    )
    app.state.world_rag_compiler_service = WorldRagCompilerService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
    )
    app.state.world_rag_sync_service = WorldRagSyncService(
        db_path=settings.DATABASE_PATH,
        compiler=app.state.world_rag_compiler_service,
    )
    app.state.historian_service = HistorianService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
        rag_sync=app.state.world_rag_sync_service,
        timeline_service=app.state.timeline_service,
    )
    logger.info("Services initialized")

    yield

    logger.info("Shutting down application")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Fable API",
        description="AI-powered worldbuilding tool with persistent memory",
        version="1.0.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(world.router, prefix="/api/world", tags=["World"])
    app.include_router(lore_entities.router, prefix="/api/lore", tags=["Lore Entities"])
    app.include_router(lore_relations.router, prefix="/api/lore", tags=["Lore Relations"])
    app.include_router(lore_notes.router, prefix="/api/lore", tags=["Lore Notes"])
    app.include_router(canon_guardian.router, prefix="/api/guardian", tags=["Canon Guardian"])
    app.include_router(historian.router, prefix="/api/historian", tags=["Historian"])
    app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
    app.include_router(timeline.router, prefix="/api/timeline", tags=["Timeline"])

    @sio.event
    async def connect(sid, environ):
        query_string = environ.get('QUERY_STRING', '')
        if 'worldId=' in query_string:
            world_id = query_string.split('worldId=')[-1].split('&')[0]
            await sio.enter_room(sid, world_id)
            logger.debug(f"Client {sid[:8]}... joined world room: {world_id[:8]}...")

    @sio.event
    async def disconnect(sid):
        logger.debug(f"Client {sid[:8]}... disconnected")

    socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "worldbuilding-companion",
            "backboard_available": app.state.backboard.is_available if hasattr(app.state, 'backboard') else False,
        }

    @app.get("/")
    async def root():
        return {
            "name": "Fable API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health"
        }

    return app
