"""Zone event ORM model — records when a tracked person crosses a zone boundary."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ZoneEvent(Base):
    __tablename__ = "zone_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    track_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    zone_name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(32), nullable=False)  # entry|exit|dwell|checkout
    # entry | exit | dwell_start | dwell_end
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # Normalized position 0.0-1.0
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
