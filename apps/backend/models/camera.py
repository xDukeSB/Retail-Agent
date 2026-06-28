"""Camera ORM model."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # active | inactive | error | connecting
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # JSON: {"zones": [{"name": "entry", "type": "line|polygon", "points": [[x,y],...]}]}
    zone_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: {"width": 1920, "height": 1080, "fps": 25}
    stream_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
