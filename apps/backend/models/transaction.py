import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

class Transaction(Base):
    __tablename__ = "transactions"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(36), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(100)) # pos, online, etc.
    status: Mapped[str] = mapped_column(String(50), default="completed")

class TransactionEvent(Base):
    __tablename__ = "transaction_events"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id", ondelete="CASCADE"))
    track_id: Mapped[str] = mapped_column(String(36), nullable=True) # matched person
    timestamp: Mapped[datetime] = mapped_column(DateTime)
