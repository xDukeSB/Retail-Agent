"""
event_repository.py — SQLAlchemy ORM models and repository for entry/exit events.

Tables:
  entry_exit_lines     — Virtual lines drawn by store owner per camera
  crossing_events      — Raw line crossing records (CUSTOMER_ENTERED / CUSTOMER_EXITED)
  visitor_sessions     — Aggregated session: entry_time, exit_time, dwell_seconds

Design choices:
  - crossing_events is append-only (never updated)
  - visitor_sessions is upserted: ENTRY creates session, EXIT updates it
  - Soft-delete is NOT used — events are permanent audit records
  - All timestamps stored as UTC unix float for precision + portability
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import (
    Boolean, Float, Index, Integer, String, Text,
    and_, func, select, update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.logging import get_logger
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

logger = get_logger(__name__)


# ── ORM Models ────────────────────────────────────────────────────────────────

class EntryExitLineModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted virtual line definition per camera."""
    __tablename__ = "entry_exit_lines"

    camera_id:      Mapped[str]   = mapped_column(String(36), nullable=False, index=True)
    name:           Mapped[str]   = mapped_column(String(100), nullable=False)
    line_type:      Mapped[str]   = mapped_column(String(20), nullable=False, default="both")

    # Normalized coordinates [0, 1]
    x1:             Mapped[float] = mapped_column(Float, nullable=False)
    y1:             Mapped[float] = mapped_column(Float, nullable=False)
    x2:             Mapped[float] = mapped_column(Float, nullable=False)
    y2:             Mapped[float] = mapped_column(Float, nullable=False)

    flip_direction: Mapped[bool]  = mapped_column(Boolean, default=False, nullable=False)
    is_active:      Mapped[bool]  = mapped_column(Boolean, default=True, nullable=False)
    min_crossings:  Mapped[int]   = mapped_column(Integer, default=1, nullable=False)
    meta_json:      Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_lines_camera_active", "camera_id", "is_active"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":             self.id,
            "camera_id":      self.camera_id,
            "name":           self.name,
            "line_type":      self.line_type,
            "x1": self.x1, "y1": self.y1,
            "x2": self.x2, "y2": self.y2,
            "flip_direction": self.flip_direction,
            "is_active":      self.is_active,
            "min_crossings":  self.min_crossings,
            "created_at":     self.created_at.isoformat(),
            "updated_at":     self.updated_at.isoformat(),
        }


class CrossingEventModel(Base, TimestampMixin):
    """Append-only log of every line crossing detected."""
    __tablename__ = "crossing_events"

    id:             Mapped[str]   = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    line_id:        Mapped[str]   = mapped_column(String(36), nullable=False, index=True)
    line_name:      Mapped[str]   = mapped_column(String(100), nullable=False)
    camera_id:      Mapped[str]   = mapped_column(String(36), nullable=False, index=True)

    # Anonymous visitor identity
    visitor_id:     Mapped[int]   = mapped_column(Integer, nullable=False, index=True)
    visitor_label:  Mapped[str]   = mapped_column(String(50), nullable=False)
    track_id:       Mapped[int]   = mapped_column(Integer, nullable=False)

    # Event classification
    event_type:     Mapped[str]   = mapped_column(String(30), nullable=False)
    direction:      Mapped[str]   = mapped_column(String(10), nullable=False)
    line_type:      Mapped[str]   = mapped_column(String(20), nullable=False)

    # Timing and position
    event_ts:       Mapped[float] = mapped_column(Float, nullable=False, index=True)
    confidence:     Mapped[float] = mapped_column(Float, nullable=False)
    position_x:     Mapped[float] = mapped_column(Float, nullable=False)
    position_y:     Mapped[float] = mapped_column(Float, nullable=False)
    synced:         Mapped[bool]  = mapped_column(Boolean, default=False, server_default='0', nullable=False)

    __table_args__ = (
        Index("ix_crossings_camera_ts", "camera_id", "event_ts"),
        Index("ix_crossings_visitor",   "visitor_id", "event_ts"),
        Index("ix_crossings_type_ts",   "event_type", "event_ts"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":            self.id,
            "line_id":       self.line_id,
            "line_name":     self.line_name,
            "camera_id":     self.camera_id,
            "visitor_id":    self.visitor_id,
            "visitor_label": self.visitor_label,
            "track_id":      self.track_id,
            "event_type":    self.event_type,
            "direction":     self.direction,
            "line_type":     self.line_type,
            "event_ts":      self.event_ts,
            "confidence":    round(self.confidence, 4),
            "position":      {"x_norm": self.position_x, "y_norm": self.position_y},
            "created_at":    self.created_at.isoformat(),
        }


class VisitorSessionModel(Base, TimestampMixin):
    """
    Aggregated visitor session.
    Created on ENTRY, updated on EXIT, finalised when track is REMOVED.
    """
    __tablename__ = "visitor_sessions"

    id:              Mapped[str]   = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id:       Mapped[str]   = mapped_column(String(36), nullable=False, index=True)

    # Anonymous identity
    visitor_id:      Mapped[int]   = mapped_column(Integer, nullable=False, index=True)
    visitor_label:   Mapped[str]   = mapped_column(String(50), nullable=False)

    # Session timing
    entry_ts:        Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_ts:         Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dwell_seconds:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Source references
    entry_line_id:   Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    exit_line_id:    Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    entry_event_id:  Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    exit_event_id:   Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Session state
    is_complete:     Mapped[bool]  = mapped_column(Boolean, default=False, nullable=False)
    confidence:      Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    __table_args__ = (
        Index("ix_sessions_camera_entry", "camera_id", "entry_ts"),
        Index("ix_sessions_visitor",      "visitor_id"),
        Index("ix_sessions_complete",     "is_complete", "camera_id"),
    )

    @property
    def entry_datetime(self) -> Optional[datetime]:
        if self.entry_ts is None:
            return None
        return datetime.fromtimestamp(self.entry_ts, tz=timezone.utc)

    @property
    def exit_datetime(self) -> Optional[datetime]:
        if self.exit_ts is None:
            return None
        return datetime.fromtimestamp(self.exit_ts, tz=timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":             self.id,
            "camera_id":      self.camera_id,
            "visitor_id":     self.visitor_id,
            "visitor_label":  self.visitor_label,
            "entry_ts":       self.entry_ts,
            "exit_ts":        self.exit_ts,
            "dwell_seconds":  round(self.dwell_seconds, 1) if self.dwell_seconds else None,
            "entry_time":     self.entry_datetime.isoformat() if self.entry_datetime else None,
            "exit_time":      self.exit_datetime.isoformat()  if self.exit_datetime  else None,
            "entry_line_id":  self.entry_line_id,
            "exit_line_id":   self.exit_line_id,
            "is_complete":    self.is_complete,
            "confidence":     round(self.confidence, 4),
        }


# ── Repository ─────────────────────────────────────────────────────────────────

class EventRepository:
    """
    All database operations for entry/exit events.
    Methods are async and accept an AsyncSession.
    Caller (EventService) controls transaction boundaries.
    """

    # ── Lines ──────────────────────────────────────────────────────────────────

    async def create_line(self, session: AsyncSession, data: dict) -> EntryExitLineModel:
        import json
        line = EntryExitLineModel(
            id=data.get("id", str(uuid.uuid4())),
            camera_id=data["camera_id"],
            name=data.get("name", "Line"),
            line_type=data.get("line_type", "both"),
            x1=float(data["x1"]), y1=float(data["y1"]),
            x2=float(data["x2"]), y2=float(data["y2"]),
            flip_direction=data.get("flip_direction", False),
            is_active=data.get("is_active", True),
            min_crossings=int(data.get("min_crossings", 1)),
            meta_json=json.dumps(data.get("meta", {})) if data.get("meta") else None,
        )
        session.add(line)
        await session.flush()
        return line

    async def get_lines_for_camera(
        self,
        session: AsyncSession,
        camera_id: str,
        active_only: bool = True,
    ) -> Sequence[EntryExitLineModel]:
        stmt = select(EntryExitLineModel).where(
            EntryExitLineModel.camera_id == camera_id
        )
        if active_only:
            stmt = stmt.where(EntryExitLineModel.is_active == True)  # noqa: E712
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_all_active_lines(
        self,
        session: AsyncSession,
    ) -> Sequence[EntryExitLineModel]:
        """Load all active lines at startup to restore detector state."""
        stmt = select(EntryExitLineModel).where(EntryExitLineModel.is_active == True)  # noqa: E712
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_line(
        self,
        session: AsyncSession,
        line_id: str,
    ) -> Optional[EntryExitLineModel]:
        result = await session.execute(
            select(EntryExitLineModel).where(EntryExitLineModel.id == line_id)
        )
        return result.scalar_one_or_none()

    async def update_line(
        self,
        session: AsyncSession,
        line_id: str,
        updates: dict,
    ) -> Optional[EntryExitLineModel]:
        import json
        line = await self.get_line(session, line_id)
        if not line:
            return None
        for key, val in updates.items():
            if key == "meta":
                line.meta_json = json.dumps(val)
            elif hasattr(line, key):
                setattr(line, key, val)
        await session.flush()
        return line

    async def delete_line(self, session: AsyncSession, line_id: str) -> bool:
        line = await self.get_line(session, line_id)
        if not line:
            return False
        await session.delete(line)
        await session.flush()
        return True

    # ── Crossing events ────────────────────────────────────────────────────────

    async def record_crossing(
        self,
        session: AsyncSession,
        crossing,   # LineCrossing dataclass
    ) -> CrossingEventModel:
        event = CrossingEventModel(
            line_id=crossing.line_id,
            line_name=crossing.line_name,
            camera_id=crossing.camera_id,
            visitor_id=crossing.visitor_id,
            visitor_label=crossing.visitor_label,
            track_id=crossing.track_id,
            event_type=crossing.event_type.value,
            direction=crossing.direction.value,
            line_type=crossing.line_type.value,
            event_ts=crossing.timestamp,
            confidence=crossing.confidence,
            position_x=crossing.position_x,
            position_y=crossing.position_y,
        )
        session.add(event)
        await session.flush()
        return event

    async def get_crossings(
        self,
        session: AsyncSession,
        camera_id: Optional[str] = None,
        event_type: Optional[str] = None,
        since_ts: Optional[float] = None,
        until_ts: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CrossingEventModel]:
        stmt = select(CrossingEventModel).order_by(CrossingEventModel.event_ts.desc())
        if camera_id:
            stmt = stmt.where(CrossingEventModel.camera_id == camera_id)
        if event_type:
            stmt = stmt.where(CrossingEventModel.event_type == event_type)
        if since_ts:
            stmt = stmt.where(CrossingEventModel.event_ts >= since_ts)
        if until_ts:
            stmt = stmt.where(CrossingEventModel.event_ts <= until_ts)
        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_crossings_today(
        self,
        session: AsyncSession,
        camera_id: str,
        event_type: Optional[str] = None,
    ) -> int:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        stmt = (
            select(func.count())
            .select_from(CrossingEventModel)
            .where(
                and_(
                    CrossingEventModel.camera_id == camera_id,
                    CrossingEventModel.event_ts >= today_start,
                )
            )
        )
        if event_type:
            stmt = stmt.where(CrossingEventModel.event_type == event_type)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    # ── Visitor sessions ───────────────────────────────────────────────────────

    async def create_or_get_session(
        self,
        session: AsyncSession,
        camera_id: str,
        visitor_id: int,
        visitor_label: str,
    ) -> VisitorSessionModel:
        """Find open (incomplete) session for this visitor, or create one."""
        stmt = (
            select(VisitorSessionModel)
            .where(
                and_(
                    VisitorSessionModel.camera_id  == camera_id,
                    VisitorSessionModel.visitor_id == visitor_id,
                    VisitorSessionModel.is_complete == False,  # noqa: E712
                )
            )
            .order_by(VisitorSessionModel.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        vs = result.scalar_one_or_none()
        if vs:
            return vs
        vs = VisitorSessionModel(
            camera_id=camera_id,
            visitor_id=visitor_id,
            visitor_label=visitor_label,
        )
        session.add(vs)
        await session.flush()
        return vs

    async def record_entry(
        self,
        session: AsyncSession,
        visitor_session: VisitorSessionModel,
        crossing_event_id: str,
        entry_ts: float,
        line_id: str,
        confidence: float,
    ) -> None:
        if visitor_session.entry_ts is None:
            visitor_session.entry_ts      = entry_ts
            visitor_session.entry_line_id = line_id
            visitor_session.entry_event_id = crossing_event_id
            visitor_session.confidence    = confidence
            await session.flush()

    async def record_exit(
        self,
        session: AsyncSession,
        visitor_session: VisitorSessionModel,
        crossing_event_id: str,
        exit_ts: float,
        line_id: str,
        confidence: float,
    ) -> None:
        visitor_session.exit_ts        = exit_ts
        visitor_session.exit_line_id   = line_id
        visitor_session.exit_event_id  = crossing_event_id
        visitor_session.is_complete    = True
        if visitor_session.entry_ts:
            visitor_session.dwell_seconds = exit_ts - visitor_session.entry_ts
        await session.flush()

    async def get_sessions(
        self,
        session: AsyncSession,
        camera_id: Optional[str] = None,
        complete_only: bool = False,
        since_ts: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[VisitorSessionModel]:
        stmt = select(VisitorSessionModel).order_by(
            VisitorSessionModel.created_at.desc()
        )
        if camera_id:
            stmt = stmt.where(VisitorSessionModel.camera_id == camera_id)
        if complete_only:
            stmt = stmt.where(VisitorSessionModel.is_complete == True)  # noqa: E712
        if since_ts:
            stmt = stmt.where(VisitorSessionModel.entry_ts >= since_ts)
        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_summary(
        self,
        session: AsyncSession,
        camera_id: str,
        since_ts: float,
    ) -> dict[str, Any]:
        """Return today's entry/exit counts and avg dwell time for a camera."""
        entries = await self.count_crossings_today(
            session, camera_id, "customer_entered"
        )
        exits = await self.count_crossings_today(
            session, camera_id, "customer_exited"
        )
        # Average dwell from complete sessions today
        stmt = (
            select(func.avg(VisitorSessionModel.dwell_seconds))
            .where(
                and_(
                    VisitorSessionModel.camera_id  == camera_id,
                    VisitorSessionModel.is_complete == True,  # noqa: E712
                    VisitorSessionModel.entry_ts   >= since_ts,
                )
            )
        )
        result   = await session.execute(stmt)
        avg_dwell = result.scalar_one_or_none()

        # Current occupancy: entries - exits today (approx)
        occupancy = max(0, entries - exits)

        return {
            "camera_id":        camera_id,
            "entries_today":    entries,
            "exits_today":      exits,
            "current_occupancy": occupancy,
            "avg_dwell_seconds": round(float(avg_dwell), 1) if avg_dwell else None,
        }


# Singleton
event_repository = EventRepository()
