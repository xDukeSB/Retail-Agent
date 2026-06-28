"""
RetailAI Agent — Production FastAPI application.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text, select

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import Role, hash_password
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.middleware.logging import LoggingMiddleware
from app.models.user import User
from app.services.camera_manager import camera_manager
from app.services.detection_pipeline import get_pipeline, DetectionPipeline
from app.services.analytics_pipeline import analytics_pipeline
from app.services.tracking_pipeline import get_tracking_pipeline
from app.services.event_service import get_event_service
from app.services.zone_analytics_service import zone_analytics_service
from app.api.v1.endpoints.websocket import register_ws_broadcaster
# Import event models so Base.metadata includes them for create_all
from app.db.event_repository import (  # noqa: F401
    EntryExitLineModel, CrossingEventModel, VisitorSessionModel
)
from app.db.timeline_repository import TimelineEventModel  # noqa: F401
from app.db.analytics_repository import DwellTimeAnalyticsModel, ZoneVisitAnalyticsModel  # noqa: F401
from app.db.checkout_repository import CheckoutAnalyticsModel  # noqa: F401

settings = get_settings()
configure_logging(level=settings.LOG_LEVEL, fmt=settings.LOG_FORMAT)
logger = get_logger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "Starting RetailAI Agent backend",
        extra={"version": settings.APP_VERSION, "env": settings.ENVIRONMENT.value},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Manual migration for synced column
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError
        tables_to_migrate = [
            "timeline_events",
            "dwell_time_analytics",
            "zone_visit_analytics",
            "checkout_analytics",
            "crossing_events"
        ]
        for table in tables_to_migrate:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN synced BOOLEAN DEFAULT 0 NOT NULL"))
            except OperationalError:
                # Column already exists
                pass

    logger.info("Database tables created/verified/migrated")

    # Bootstrap admin user if DB is empty
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).limit(1))
        if not result.scalar_one_or_none():
            admin = User(
                email=settings.ADMIN_EMAIL,
                full_name=settings.ADMIN_NAME,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role=Role.ADMIN.value,
                is_active=True,
                is_verified=True,
                must_change_password=True,
            )
            db.add(admin)
            await db.commit()
            logger.info(
                "Default admin user created",
                extra={"email": settings.ADMIN_EMAIL, "note": "Change password on first login"},
            )

    # 1 — Start camera ingestion
    await camera_manager.start(AsyncSessionLocal)
    logger.info("CameraManager started")

    # 2 — Start Multiprocessing Inference Engine (YOLOv11 + ByteTrack)
    from inference_engine.engine_manager import engine_manager
    engine_manager.start()
    
    # 3 — Start tracking pipeline bridge
    tracking_pipeline = get_tracking_pipeline()
    await tracking_pipeline.start()
    logger.info("TrackingPipeline bridge started")

    # 4 — Start event service (entry/exit line crossing)
    event_service = get_event_service()
    await event_service.start(tracking_pipeline)
    logger.info("EventService started")

    # 5 — Start analytics pipeline
    # Note: Analytics Pipeline still expects detection frames, we'll need to adapt it
    # await analytics_pipeline.start(detection_pipeline) 
    # logger.info("AnalyticsPipeline started")

    # 5.5 — Start zone analytics service
    await zone_analytics_service.start(tracking_pipeline)
    logger.info("ZoneAnalyticsService started")

    # 5.6 — Start checkout analytics service
    from app.services.checkout_analytics_service import checkout_analytics_service
    await checkout_analytics_service.start(tracking_pipeline)
    logger.info("CheckoutAnalyticsService started")

    # 6 — Register WebSocket broadcaster
    register_ws_broadcaster()
    logger.info("WebSocket broadcaster registered")

    # 7 — Start Offline-First Sync Engine
    from app.services.sync_service import sync_service
    await sync_service.start()

    yield

    # —— Shutdown (reverse order) ————————————————————
    logger.info("Shutting down RetailAI Agent backend")
    await sync_service.stop()
    await checkout_analytics_service.stop(tracking_pipeline)
    await zone_analytics_service.stop(tracking_pipeline)
    # await analytics_pipeline.stop(detection_pipeline)
    await event_service.stop(tracking_pipeline)
    await tracking_pipeline.stop()
    await engine_manager.stop()
    await camera_manager.stop()
    await engine.dispose()


# ── App factory ────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Local-First Retail Intelligence Platform — API",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost first) ───────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Response-Time"],
    )
    app.add_middleware(LoggingMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(v1_router, prefix="/api")

    # ── Observability ─────────────────────────────────────────────────────────
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # ── Global exception handlers ─────────────────────────────────────────────
    @app.exception_handler(404)
    async def not_found(_req: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Resource not found", "path": str(_req.url.path)},
        )

    @app.exception_handler(500)
    async def internal_error(_req: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # ── Root endpoint ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs":    "/api/docs",
            "health":  "/api/v1/health",
        }

    return app


app = create_app()
