"""
timeline_repository.py — SQLAlchemy models and repository for timeline events.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from sqlalchemy import Float, Index, Integer, String, Text, select, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

class TimelineEventModel(Base, TimestampMixin):
    """
    Table for generic timeline events like 'Customer Entered', 'Queue Detected'.
    """
    __tablename__ = "timeline_events"

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    camera_id:  Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp:  Mapped[float] = mapped_column(Float, nullable=False, index=True)
    visitor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    details:    Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    synced:     Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)

    __table_args__ = (
        Index("ix_timeline_cam_ts", "camera_id", "timestamp"),
    )

    def to_dict(self) -> dict[str, Any]:
        import json
        details_dict = {}
        if self.details:
            try:
                details_dict = json.loads(self.details)
            except json.JSONDecodeError:
                details_dict = {"raw": self.details}

        return {
            "id":         self.id,
            "event_type": self.event_type,
            "camera_id":  self.camera_id,
            "timestamp":  self.timestamp,
            "visitor_id": self.visitor_id,
            "details":    details_dict,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class TimelineRepository:
    async def create_event(
        self,
        session: AsyncSession,
        event_type: str,
        camera_id: str,
        timestamp: float,
        visitor_id: Optional[int] = None,
        details: Optional[str] = None
    ) -> TimelineEventModel:
        record = TimelineEventModel(
            event_type=event_type,
            camera_id=camera_id,
            timestamp=timestamp,
            visitor_id=visitor_id,
            details=details,
        )
        session.add(record)
        await session.flush()
        return record

    async def get_events(
        self,
        session: AsyncSession,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        camera_id: Optional[str] = None,
        event_types: Optional[list[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[TimelineEventModel]:
        stmt = select(TimelineEventModel)
        
        if start_ts is not None:
            stmt = stmt.where(TimelineEventModel.timestamp >= start_ts)
        if end_ts is not None:
            stmt = stmt.where(TimelineEventModel.timestamp <= end_ts)
        if camera_id is not None:
            stmt = stmt.where(TimelineEventModel.camera_id == camera_id)
        if event_types and len(event_types) > 0:
            stmt = stmt.where(TimelineEventModel.event_type.in_(event_types))
            
        stmt = stmt.order_by(TimelineEventModel.timestamp.desc())
        stmt = stmt.offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        return result.scalars().all()

timeline_repository = TimelineRepository()
