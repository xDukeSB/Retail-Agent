import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

class Store(Base):
    __tablename__ = "stores"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), default="Downtown Flagship")
    region: Mapped[str] = mapped_column(String(255), nullable=True, default="North America - West")
    address: Mapped[str] = mapped_column(String(500), nullable=True, default="123 Market St, San Francisco, CA")
    timezone: Mapped[str] = mapped_column(String(100), default="America/Los_Angeles")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    last_sync: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # Sync Toggles
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_metadata: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_analytics: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_reports: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_video: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Feature Toggles
    queue_detection: Mapped[bool] = mapped_column(Boolean, default=True)
    transaction_detection: Mapped[bool] = mapped_column(Boolean, default=True)
    heatmap_generation: Mapped[bool] = mapped_column(Boolean, default=True)
    zone_tracking: Mapped[bool] = mapped_column(Boolean, default=True)
    face_anonymization: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # AI Engine Settings
    detection_confidence: Mapped[float] = mapped_column(Float, default=0.6)
    frame_evaluation_rate: Mapped[int] = mapped_column(Integer, default=5)
