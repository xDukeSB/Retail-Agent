import uuid
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

class CloudSyncQueue(Base):
    __tablename__ = "cloud_sync_queue"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_name: Mapped[str] = mapped_column(String(100), index=True)
    record_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(50)) # insert, update, delete
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True) # pending, synced, error
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
