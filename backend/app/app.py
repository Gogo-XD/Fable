"""
Worldbuilding Companion - FastAPI Backend
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.config import settings
from app.database.db import init_db
from app.logging import setup_logging, get_logger
from app.routers import (
    graph,
    lore_entities,
    lore_notes,
    lore_relations,
    world,
)
from app.services.backboard import BackboardService
from app.services.graph import GraphService
from app.services.lore import LoreService
from app.services.world import WorldService

logger = get_logger('main')

# Socket.IO server for real-time graph updates
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting Worldbuilding Companion API")

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
    app.state.lore_service = LoreService(
        db_path=settings.DATABASE_PATH,
        backboard=backboard,
    )
    app.state.graph_service = GraphService(
        db_path=settings.DATABASE_PATH,
    )
    logger.info("Services initialized")

    yield

    logger.info("Shutting down application")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Worldbuilding Companion API",
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
    app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])

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
            "name": "Worldbuilding Companion API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health"
        }

    return app
