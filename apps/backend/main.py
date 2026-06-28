"""
RetailAI Agent — FastAPI Backend
Local-First Retail Intelligence Platform
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Depends

from database import init_db, engine
from routers import cameras, analytics, events, reports, streams, websocket, auth, cloud
from services.aggregator import AggregatorService
from services.auth import allow_viewer, allow_manager, allow_admin
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("retailai")

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown lifecycle."""
    logger.info("🚀 RetailAI Agent backend starting...")
    await init_db()
    
    # Create default admin user if missing
    from sqlalchemy.ext.asyncio import AsyncSession
    from database import AsyncSessionLocal
    from sqlalchemy import select
    from models.user import User
    from services.auth import get_password_hash
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "admin@retailai.local"))
        if not result.scalar_one_or_none():
            admin = User(email="admin@retailai.local", hashed_password=get_password_hash("admin123"), full_name="System Admin", role="admin")
            db.add(admin)
            await db.commit()
            
    # Create default store config if missing
    from models.store import Store
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Store))
        if not result.scalars().first():
            store = Store(name="Downtown Flagship")
            db.add(store)
            await db.commit()

    aggregator = AggregatorService()
    aggregator_task = asyncio.create_task(aggregator.run_loop())
    
    from services.cloud_sync import CloudSyncService
    cloud_sync = CloudSyncService()
    cloud_sync_task = asyncio.create_task(cloud_sync.run_loop())
    
    # Start CV Pipeline
    from services.cv_pipeline.engine_manager import engine_manager
    engine_manager.start()
    # start_async() must be called from inside an async context to safely create asyncio tasks
    await engine_manager.start_async()
    
    from services.cv_pipeline.event_engine import EventEngine
    event_engine = EventEngine()
    event_engine_task = asyncio.create_task(event_engine.run_loop())
    
    # Load all enabled cameras into the CV pipeline
    async with AsyncSessionLocal() as db:
        from models.camera import Camera
        result = await db.execute(select(Camera).where(Camera.is_enabled == True))
        loaded = 0
        for cam in result.scalars():
            engine_manager.add_camera(str(cam.id), cam.rtsp_url)
            loaded += 1
        logger.info(f"[Startup] Loaded {loaded} enabled camera(s) into CV pipeline.")

    logger.info("✅ Backend ready — local-first mode active")
    yield
    aggregator_task.cancel()
    cloud_sync_task.cancel()
    event_engine_task.cancel()
    await event_engine.stop()
    await engine_manager.stop()
    await engine.dispose()
    logger.info("👋 Backend shutdown complete")


app = FastAPI(
    title="RetailAI Agent API",
    description="Local-First Retail Intelligence Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware ────────────────────────────────────────────────────────────────
@app.middleware("http")
async def secure_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

from routers import cameras, analytics, events, reports, streams, websocket, auth, cloud, transactions, settings
from routers import transaction_intelligence as txn_intelligence_router

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(cloud.router, prefix="/api/v1/cloud", tags=["Cloud"], dependencies=[Depends(allow_admin)])
app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["Transactions"])
app.include_router(
    txn_intelligence_router.router,
    prefix="/api/v1/transactions/intelligence",
    tags=["Transaction Intelligence"],
    dependencies=[Depends(allow_viewer)],
)
app.include_router(cameras.router,   prefix="/api/v1/cameras",   tags=["Cameras"], dependencies=[Depends(allow_manager)])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"], dependencies=[Depends(allow_viewer)])
app.include_router(events.router,    prefix="/api/v1/events",    tags=["Events"]) # Events are posted by CV pipeline, usually uses machine tokens
app.include_router(reports.router,   prefix="/api/v1/reports",   tags=["Reports"], dependencies=[Depends(allow_viewer)])
app.include_router(streams.router,   prefix="/api/v1/streams",   tags=["Streams"])
app.include_router(websocket.router, prefix="/ws",               tags=["WebSocket"])
app.include_router(settings.router,  prefix="/api/v1/settings",  tags=["Settings"], dependencies=[Depends(allow_viewer)])

@app.get("/api/health", tags=["Health"])
@limiter.limit("10/minute")
async def health(request: Request):
    from sqlalchemy.ext.asyncio import AsyncSession
    from database import AsyncSessionLocal
    from sqlalchemy import select, func
    from models.camera import Camera
    
    # Compute live health score from camera status
    try:
        async with AsyncSessionLocal() as db:
            total_result = await db.execute(select(func.count(Camera.id)).where(Camera.is_enabled == True))
            total = total_result.scalar() or 0
            active_result = await db.execute(select(func.count(Camera.id)).where(Camera.is_enabled == True, Camera.status == "active"))
            active = active_result.scalar() or 0
            score = round((active / total) * 100) if total > 0 else 0
    except Exception:
        score = 0
    
    return {
        "status": "ok",
        "version": "1.0.0",
        "mode": "local-first",
        "cloud_sync": settings.CLOUD_SYNC_ENABLED,
        "score": score,
    }


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "RetailAI Agent API", "docs": "/api/docs"}
