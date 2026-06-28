"""Analytics aggregation ORM models."""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class HourlyCount(Base):
    """Pre-aggregated hourly traffic metrics per camera."""
    __tablename__ = "hourly_counts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    hour: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    entries: Mapped[int] = mapped_column(Integer, default=0)
    exits: Mapped[int] = mapped_column(Integer, default=0)
    peak_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tracks: Mapped[int] = mapped_column(Integer, default=0)
    avg_dwell_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    max_dwell_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class HeatmapCell(Base):
    """Spatial density grid — tracks where customers spend time."""
    __tablename__ = "heatmap_cells"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    # Grid cell position (0–99 for a 100x100 grid)
    cell_x: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_y: Mapped[int] = mapped_column(Integer, nullable=False)
    density: Mapped[float] = mapped_column(Float, default=0.0)
    visit_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class QueueSnapshot(Base):
    """Queue depth and wait time per zone per minute."""
    __tablename__ = "queue_snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    zone_name: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    queue_depth: Mapped[int] = mapped_column(Integer, default=0)
    avg_wait_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_wait_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class DailyReport(Base):
    """Daily summary — pre-computed for fast dashboard loading."""
    __tablename__ = "daily_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    total_entries: Mapped[int] = mapped_column(Integer, default=0)
    total_exits: Mapped[int] = mapped_column(Integer, default=0)
    unique_visitors: Mapped[int] = mapped_column(Integer, default=0)
    avg_dwell_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    peak_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    peak_count: Mapped[int] = mapped_column(Integer, default=0)
    conversion_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
