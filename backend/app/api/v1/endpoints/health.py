"""
Health check endpoints — comprehensive system status.
"""
from __future__ import annotations

import os
import platform
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.logging import get_logger

logger   = get_logger(__name__)
router   = APIRouter(prefix="/health", tags=["Health"])
settings = get_settings()
_START_TIME = time.time()


class ComponentHealth(BaseModel):
    status:  str   # "ok" | "degraded" | "down"
    latency_ms: float | None = None
    detail:  str | None = None


class HealthResponse(BaseModel):
    status:     str
    version:    str
    environment: str
    uptime_seconds: float
    timestamp:  str
    components: dict[str, ComponentHealth]


@router.get("/", response_model=HealthResponse, summary="Full health check")
async def health_check(db: AsyncSession = Depends(get_db)):
    components: dict[str, ComponentHealth] = {}

    # ── Database ──────────────────────────────────────────────────────
    db_start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        components["database"] = ComponentHealth(
            status="ok",
            latency_ms=round((time.perf_counter() - db_start) * 1000, 2),
            detail=settings.DB_DIALECT.value,
        )
    except Exception as exc:
        components["database"] = ComponentHealth(status="down", detail=str(exc))

    # ── Disk ──────────────────────────────────────────────────────────
    try:
        stat   = os.statvfs(".")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        components["disk"] = ComponentHealth(
            status="ok" if free_gb > 1 else "degraded",
            detail=f"{free_gb:.1f} GB free",
        )
    except Exception as exc:
        components["disk"] = ComponentHealth(status="degraded", detail=str(exc))

    # ── Memory ────────────────────────────────────────────────────────
    try:
        import psutil  # optional
        mem = psutil.virtual_memory()
        components["memory"] = ComponentHealth(
            status="ok" if mem.percent < 90 else "degraded",
            detail=f"{mem.percent:.1f}% used ({mem.available // 1024 // 1024} MB free)",
        )
    except ImportError:
        components["memory"] = ComponentHealth(status="ok", detail="psutil not installed")

    overall = "ok" if all(c.status == "ok" for c in components.values()) else \
              "degraded" if any(c.status == "ok" for c in components.values()) else "down"

    return HealthResponse(
        status=overall,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT.value,
        uptime_seconds=round(time.time() - _START_TIME, 1),
        timestamp=datetime.now(timezone.utc).isoformat(),
        components=components,
    )


@router.get("/ready", summary="Readiness probe (K8s/Docker)")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Lightweight DB ping — used by Docker HEALTHCHECK."""
    await db.execute(text("SELECT 1"))
    return {"ready": True}


@router.get("/live", summary="Liveness probe (K8s/Docker)")
async def liveness():
    """Process is alive — no external deps checked."""
    return {"alive": True}
