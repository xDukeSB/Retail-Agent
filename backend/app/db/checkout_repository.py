"""
checkout_repository.py — SQLAlchemy ORM models and repository for checkout analytics.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from sqlalchemy import Float, Index, Integer, String, select, func, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

class CheckoutAnalyticsModel(Base, TimestampMixin):
    """
    Dedicated analytics table for storing visitor checkout sessions.
    Real-time write from CheckoutAnalyticsService.
    """
    __tablename__ = "checkout_analytics"

    id:                   Mapped[str]   = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id:            Mapped[str]   = mapped_column(String(36), nullable=False, index=True)
    visitor_id:           Mapped[int]   = mapped_column(Integer, nullable=False, index=True)
    entry_ts:             Mapped[float] = mapped_column(Float, nullable=False)
    exit_ts:              Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds:     Mapped[float] = mapped_column(Float, nullable=False)
    purchase_probability: Mapped[float] = mapped_column(Float, nullable=False) # 0.0 to 1.0
    confidence_score:     Mapped[float] = mapped_column(Float, nullable=False) # 0.0 to 1.0
    synced:               Mapped[bool]  = mapped_column(Boolean, default=False, server_default='0', nullable=False)

    __table_args__ = (
        Index("ix_checkout_analytics_cam_exit", "camera_id", "exit_ts"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":                   self.id,
            "camera_id":            self.camera_id,
            "visitor_id":           self.visitor_id,
            "entry_ts":             self.entry_ts,
            "exit_ts":              self.exit_ts,
            "duration_seconds":     round(self.duration_seconds, 1),
            "purchase_probability": round(self.purchase_probability, 2),
            "confidence_score":     round(self.confidence_score, 2),
            "created_at":           self.created_at.isoformat() if self.created_at else None,
        }

class CheckoutAnalyticsRepository:
    async def save_checkout_session(
        self,
        session: AsyncSession,
        camera_id: str,
        visitor_id: int,
        entry_ts: float,
        exit_ts: float,
        duration_seconds: float,
        purchase_probability: float,
        confidence_score: float,
    ) -> CheckoutAnalyticsModel:
        record = CheckoutAnalyticsModel(
            camera_id=camera_id,
            visitor_id=visitor_id,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            duration_seconds=duration_seconds,
            purchase_probability=purchase_probability,
            confidence_score=confidence_score
        )
        session.add(record)
        await session.flush()
        return record

    async def get_metrics(
        self,
        session: AsyncSession,
        camera_id: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None
    ) -> dict[str, Any]:
        stmt = select(
            func.count(CheckoutAnalyticsModel.id),
            func.avg(CheckoutAnalyticsModel.duration_seconds),
            func.avg(CheckoutAnalyticsModel.purchase_probability)
        )
        
        if camera_id:
            stmt = stmt.where(CheckoutAnalyticsModel.camera_id == camera_id)
        if start_ts is not None:
            stmt = stmt.where(CheckoutAnalyticsModel.entry_ts >= start_ts)
        if end_ts is not None:
            stmt = stmt.where(CheckoutAnalyticsModel.entry_ts <= end_ts)

        result = await session.execute(stmt)
        row = result.fetchone()
        
        return {
            "total_checkout_visitors": row[0] or 0,
            "average_checkout_duration_seconds": round(row[1] or 0.0, 1),
            "average_purchase_probability": round(row[2] or 0.0, 2),
        }

    async def get_sessions(
        self,
        session: AsyncSession,
        camera_id: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[CheckoutAnalyticsModel]:
        stmt = select(CheckoutAnalyticsModel)
        
        if camera_id:
            stmt = stmt.where(CheckoutAnalyticsModel.camera_id == camera_id)
        if start_ts is not None:
            stmt = stmt.where(CheckoutAnalyticsModel.entry_ts >= start_ts)
        if end_ts is not None:
            stmt = stmt.where(CheckoutAnalyticsModel.entry_ts <= end_ts)

        stmt = stmt.order_by(CheckoutAnalyticsModel.entry_ts.desc())
        stmt = stmt.offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        return result.scalars().all()

checkout_repository = CheckoutAnalyticsRepository()
