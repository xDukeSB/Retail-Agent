"""
camera_repository.py — Formal repository layer for camera data access.

Separates raw DB operations from business logic. All methods are
async and receive an explicit AsyncSession so they compose cleanly
with FastAPI's dependency injection.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.camera_registry import Camera

logger = get_logger(__name__)


class CameraRepository:
    """
    Data-access layer for Camera records.
    One method = one DB operation. No business logic here.
    """

    # ── Queries ───────────────────────────────────────────────────────────────

    async def find_all(
        self,
        db: AsyncSession,
        *,
        is_active: bool | None = True,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[int, list[Camera]]:
        """Returns (total_count, page_of_cameras)."""
        q = select(Camera)
        if is_active is not None:
            q = q.where(Camera.is_active == is_active)
        if status:
            q = q.where(Camera.status == status)

        total = (await db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        cameras = (await db.execute(
            q.order_by(Camera.created_at.asc()).offset(offset).limit(limit)
        )).scalars().all()

        return total, list(cameras)

    async def find_by_id(self, db: AsyncSession, camera_id: str) -> Camera | None:
        result = await db.execute(select(Camera).where(Camera.id == camera_id))
        return result.scalar_one_or_none()

    async def find_by_name(self, db: AsyncSession, name: str) -> Camera | None:
        result = await db.execute(select(Camera).where(Camera.name == name))
        return result.scalar_one_or_none()

    async def find_by_rtsp_url(self, db: AsyncSession, rtsp_url: str) -> Camera | None:
        result = await db.execute(select(Camera).where(Camera.rtsp_url == rtsp_url))
        return result.scalar_one_or_none()

    async def count_by_status(self, db: AsyncSession) -> dict[str, int]:
        result = await db.execute(
            select(Camera.status, func.count(Camera.id))
            .where(Camera.is_active == True)  # noqa: E712
            .group_by(Camera.status)
        )
        return {row[0]: row[1] for row in result.all()}

    # ── Commands ──────────────────────────────────────────────────────────────

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Camera:
        data.setdefault("id", str(uuid.uuid4()))
        camera = Camera(**data)
        db.add(camera)
        await db.commit()
        await db.refresh(camera)
        logger.info("Camera created", extra={"camera_id": camera.id, "name": camera.name})
        return camera

    async def update(
        self,
        db: AsyncSession,
        camera_id: str,
        data: dict[str, Any],
    ) -> Camera | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await db.execute(update(Camera).where(Camera.id == camera_id).values(**data))
        await db.commit()
        return await self.find_by_id(db, camera_id)

    async def delete(self, db: AsyncSession, camera_id: str) -> bool:
        result = await db.execute(delete(Camera).where(Camera.id == camera_id))
        await db.commit()
        return result.rowcount > 0

    async def soft_delete(self, db: AsyncSession, camera_id: str) -> bool:
        """Mark as inactive instead of physical delete."""
        result = await db.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(is_active=False, status="inactive", updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return result.rowcount > 0

    async def update_health(
        self,
        db: AsyncSession,
        camera_id: str,
        *,
        status: str,
        avg_fps: float | None = None,
        health_score: float | None = None,
        last_error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if status == "active":
            values["last_seen_at"] = datetime.now(timezone.utc)
        if avg_fps is not None:
            values["avg_fps"] = round(avg_fps, 2)
        if health_score is not None:
            values["health_score"] = round(health_score, 1)
        if last_error is not None:
            values["last_error"] = last_error
        await db.execute(update(Camera).where(Camera.id == camera_id).values(**values))
        await db.commit()

    async def increment_reconnect_count(self, db: AsyncSession, camera_id: str) -> None:
        camera = await self.find_by_id(db, camera_id)
        if camera:
            await db.execute(
                update(Camera)
                .where(Camera.id == camera_id)
                .values(reconnect_count=camera.reconnect_count + 1)
            )
            await db.commit()


# Singleton
camera_repo = CameraRepository()
