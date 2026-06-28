"""
camera_registry.py — Database-backed camera registry.

Persists camera configurations, RTSP URLs, zone configs, and runtime
status to SQLite/PostgreSQL. Provides the single source of truth for
all camera definitions in the system.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, Float, select, update, delete
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.logging import get_logger
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

logger = get_logger(__name__)


from app.db.crypto import EncryptedString

# ── ORM Model ─────────────────────────────────────────────────────────────────

class Camera(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistent camera record — one row per physical camera."""
    __tablename__ = "cameras"

    # Identity
    name:        Mapped[str]        = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Connection (Encrypted at rest)
    rtsp_url:    Mapped[str]        = mapped_column(EncryptedString(1024), nullable=False)
    username:    Mapped[Optional[str]] = mapped_column(EncryptedString(255), nullable=True)
    password:    Mapped[Optional[str]] = mapped_column(EncryptedString(255), nullable=True)

    # Stream settings
    fps_target:  Mapped[int]        = mapped_column(Integer, default=10, nullable=False)
    resolution_w: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolution_h: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buffer_size:  Mapped[int]       = mapped_column(Integer, default=30, nullable=False)

    # Runtime state (updated by CameraService)
    status:           Mapped[str]        = mapped_column(String(32), default="inactive", nullable=False)
    # inactive | connecting | active | degraded | error | disconnected
    last_seen_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error:       Mapped[Optional[str]]      = mapped_column(Text, nullable=True)
    reconnect_count:  Mapped[int]             = mapped_column(Integer, default=0, nullable=False)
    avg_fps:          Mapped[Optional[float]]    = mapped_column(Float, nullable=True)
    health_score:     Mapped[Optional[float]]    = mapped_column(Float, nullable=True)  # 0.0–100.0

    # Zone configuration (JSON blob)
    zone_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Flags
    is_active:  Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def zones(self) -> dict[str, Any]:
        if self.zone_config:
            try:
                return json.loads(self.zone_config)
            except json.JSONDecodeError:
                return {}
        return {}

    def __repr__(self) -> str:
        return f"<Camera id={self.id[:8]} name={self.name!r} status={self.status}>"


# ── Registry ───────────────────────────────────────────────────────────────────

class CameraRegistry:
    """
    CRUD interface for camera records. Stateless — receives an
    AsyncSession per call so it works cleanly with FastAPI's DI.
    """

    async def list_cameras(
        self,
        db: AsyncSession,
        include_inactive: bool = False,
    ) -> list[Camera]:
        q = select(Camera)
        if not include_inactive:
            q = q.where(Camera.is_active == True)  # noqa: E712
        q = q.order_by(Camera.created_at.asc())
        result = await db.execute(q)
        return list(result.scalars().all())

    async def get_camera(self, db: AsyncSession, camera_id: str) -> Camera | None:
        result = await db.execute(select(Camera).where(Camera.id == camera_id))
        return result.scalar_one_or_none()

    async def get_camera_by_name(self, db: AsyncSession, name: str) -> Camera | None:
        result = await db.execute(select(Camera).where(Camera.name == name))
        return result.scalar_one_or_none()

    async def create_camera(self, db: AsyncSession, data: dict[str, Any]) -> Camera:
        camera = Camera(id=str(uuid.uuid4()), **data)
        db.add(camera)
        await db.commit()
        await db.refresh(camera)
        logger.info("Camera registered", extra={"camera_id": camera.id, "name": camera.name})
        return camera

    async def update_camera(
        self,
        db: AsyncSession,
        camera_id: str,
        data: dict[str, Any],
    ) -> Camera | None:
        await db.execute(
            update(Camera).where(Camera.id == camera_id).values(**data)
        )
        await db.commit()
        return await self.get_camera(db, camera_id)

    async def delete_camera(self, db: AsyncSession, camera_id: str) -> bool:
        result = await db.execute(
            delete(Camera).where(Camera.id == camera_id)
        )
        await db.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Camera deleted", extra={"camera_id": camera_id})
        return deleted

    async def update_status(
        self,
        db: AsyncSession,
        camera_id: str,
        status: str,
        error: str | None = None,
        avg_fps: float | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "last_error": error,
        }
        if status == "active":
            values["last_seen_at"] = datetime.now(timezone.utc)
        if avg_fps is not None:
            values["avg_fps"] = avg_fps
        await db.execute(update(Camera).where(Camera.id == camera_id).values(**values))
        await db.commit()

    async def increment_reconnect(self, db: AsyncSession, camera_id: str) -> None:
        result = await db.execute(select(Camera.reconnect_count).where(Camera.id == camera_id))
        count = result.scalar_one_or_none() or 0
        await db.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(reconnect_count=count + 1)
        )
        await db.commit()


# Singleton registry instance
registry = CameraRegistry()
