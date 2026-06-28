"""Anonymous person track ORM model."""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PersonTrack(Base):
    """
    Represents one anonymous visitor's session in the store.
    No biometric data, no identity — only movement metadata.
    """
    __tablename__ = "person_tracks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # Ephemeral ID from ByteTrack — resets each pipeline session, not stored permanently
    session_track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dwell_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # JSON: ["entry", "aisle_a", "checkout"] — zone names visited in order
    zones_visited: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: [[x_norm, y_norm, unix_ts], ...] — normalized 0-1 coordinates
    path_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    is_complete: Mapped[bool] = mapped_column(default=False)
