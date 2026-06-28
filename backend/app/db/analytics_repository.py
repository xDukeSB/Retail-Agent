"""
analytics_repository.py — SQLAlchemy ORM models and repository for dwell time analytics.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from sqlalchemy import Float, Index, Integer, String, select, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DwellTimeAnalyticsModel(Base, TimestampMixin):
    """
    Dedicated analytics table for storing completed visitor dwell times.
    Real-time write from EventService upon visitor exit.
    """
    __tablename__ = "dwell_time_analytics"

    id:               Mapped[str]   = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id:        Mapped[str]   = mapped_column(String(36), nullable=False, index=True)
    visitor_id:       Mapped[int]   = mapped_column(Integer, nullable=False, index=True)
    entry_ts:         Mapped[float] = mapped_column(Float, nullable=False)
    exit_ts:          Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    synced:           Mapped[bool]  = mapped_column(Boolean, default=False, server_default='0', nullable=False)

    __table_args__ = (
        Index("ix_dwell_analytics_cam_exit", "camera_id", "exit_ts"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":               self.id,
            "camera_id":        self.camera_id,
            "visitor_id":       self.visitor_id,
            "entry_ts":         self.entry_ts,
            "exit_ts":          self.exit_ts,
            "duration_seconds": round(self.duration_seconds, 1),
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }


class ZoneVisitAnalyticsModel(Base, TimestampMixin):
    """
    Dedicated analytics table for storing visitor zone sessions.
    Real-time write from ZoneAnalyticsService upon visitor leaving a zone.
    """
    __tablename__ = "zone_visit_analytics"

    id:               Mapped[str]   = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id:        Mapped[str]   = mapped_column(String(36), nullable=False, index=True)
    visitor_id:       Mapped[int]   = mapped_column(Integer, nullable=False, index=True)
    zone_id:          Mapped[str]   = mapped_column(String(255), nullable=False, index=True)
    zone_type:        Mapped[str]   = mapped_column(String(50), nullable=False)
    entry_ts:         Mapped[float] = mapped_column(Float, nullable=False)
    exit_ts:          Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    synced:           Mapped[bool]  = mapped_column(Boolean, default=False, server_default='0', nullable=False)

    __table_args__ = (
        Index("ix_zone_analytics_cam_exit", "camera_id", "exit_ts"),
        Index("ix_zone_analytics_zone_exit", "zone_id", "exit_ts"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":               self.id,
            "camera_id":        self.camera_id,
            "visitor_id":       self.visitor_id,
            "zone_id":          self.zone_id,
            "zone_type":        self.zone_type,
            "entry_ts":         self.entry_ts,
            "exit_ts":          self.exit_ts,
            "duration_seconds": round(self.duration_seconds, 1),
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }


class AnalyticsRepository:
    """Database operations for the analytics engine."""

    async def save_dwell_time_record(
        self,
        session: AsyncSession,
        camera_id: str,
        visitor_id: int,
        entry_ts: float,
        exit_ts: float,
        duration_seconds: float,
    ) -> DwellTimeAnalyticsModel:
        record = DwellTimeAnalyticsModel(
            camera_id=camera_id,
            visitor_id=visitor_id,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            duration_seconds=duration_seconds,
        )
        session.add(record)
        await session.flush()
        return record

    async def get_dwell_time_records(
        self,
        session: AsyncSession,
        camera_id: str,
        since_ts: float,
        until_ts: Optional[float] = None,
    ) -> Sequence[DwellTimeAnalyticsModel]:
        """Fetch records for a camera within an exit_ts time range."""
        stmt = select(DwellTimeAnalyticsModel).where(
            DwellTimeAnalyticsModel.camera_id == camera_id,
            DwellTimeAnalyticsModel.exit_ts >= since_ts
        )
        if until_ts:
            stmt = stmt.where(DwellTimeAnalyticsModel.exit_ts <= until_ts)
        
        result = await session.execute(stmt)
        return result.scalars().all()

    async def save_zone_visit_record(
        self,
        session: AsyncSession,
        camera_id: str,
        visitor_id: int,
        zone_id: str,
        zone_type: str,
        entry_ts: float,
        exit_ts: float,
        duration_seconds: float,
    ) -> ZoneVisitAnalyticsModel:
        record = ZoneVisitAnalyticsModel(
            camera_id=camera_id,
            visitor_id=visitor_id,
            zone_id=zone_id,
            zone_type=zone_type,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            duration_seconds=duration_seconds,
        )
        session.add(record)
        await session.flush()
        return record

    async def get_zone_visit_records(
        self,
        session: AsyncSession,
        camera_id: str,
        since_ts: float,
        until_ts: Optional[float] = None,
    ) -> Sequence[ZoneVisitAnalyticsModel]:
        """Fetch zone records for a camera within an exit_ts time range."""
        stmt = select(ZoneVisitAnalyticsModel).where(
            ZoneVisitAnalyticsModel.camera_id == camera_id,
            ZoneVisitAnalyticsModel.exit_ts >= since_ts
        )
        if until_ts:
            stmt = stmt.where(ZoneVisitAnalyticsModel.exit_ts <= until_ts)
        
        result = await session.execute(stmt)
        return result.scalars().all()


analytics_repository = AnalyticsRepository()
