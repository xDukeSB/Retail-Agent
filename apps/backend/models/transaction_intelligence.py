"""
Transaction Intelligence ORM models.

Extends the existing SQLite schema with transaction-specific tables.
These models power the Transaction Intelligence Engine — a per-visitor
state machine that estimates purchase likelihood from CV events.

DO NOT confuse with the existing 'transactions' table (used for POS records).
These models track *inferred* transaction intent from camera analytics.
"""
import uuid
from datetime import date as PyDate, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TransactionSession(Base):
    """
    One session per visitor (ByteTrack track_id) per camera visit.

    Lifecycle: ENTERED_STORE → ... → EXITED_STORE
    Persisted immediately when visitor first seen, updated continuously.
    """
    __tablename__ = "transaction_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # The PersonTrack.id (UUID) from the analytics tracker — links to existing track data
    visitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # Ephemeral ByteTrack integer ID (not persisted permanently, for in-memory correlation)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # State machine state
    state: Mapped[str] = mapped_column(
        String(64), default="ENTERED_STORE", nullable=False
    )

    # Confidence scoring
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    transaction_probability: Mapped[float] = mapped_column(Float, default=0.0)
    # UNLIKELY | LOW | MEDIUM | HIGH
    confidence_level: Mapped[str] = mapped_column(String(32), default="UNLIKELY")

    # JSON: ["checkout_zone_entered", "queue_completed", ...]
    detected_signals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    # Cloud sync integration — uses existing CloudSyncQueue mechanism
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    __table_args__ = (
        Index("ix_txn_session_camera_date", "camera_id", "entered_at"),
    )


class TransactionSignal(Base):
    """
    Individual signal detection event within a session.
    One row per signal detected per visitor.
    """
    __tablename__ = "transaction_signals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Signal types (matches Signal Engine definition):
    # checkout_zone_entered | queue_completed | cash_exchange_detected
    # card_machine_interaction | upi_payment_interaction
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    zone_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Normalized centroid where signal was detected
    x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Extra context: dwell time, interaction count, etc.
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class TransactionPrediction(Base):
    """
    Snapshot of prediction state at a given moment.
    Written whenever confidence level changes (UNLIKELY → LOW → MEDIUM → HIGH).
    Used for historical analysis and cloud sync.
    """
    __tablename__ = "transaction_predictions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    visitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(36), nullable=False)
    store_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    transaction_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(32), nullable=False)

    # JSON snapshot of all detected signals at prediction time
    detected_signals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class TransactionStatistic(Base):
    """
    Pre-aggregated hourly and daily rollups for fast dashboard loading.
    Computed by the AggregatorService extension (added to aggregator.py).
    """
    __tablename__ = "transaction_statistics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    camera_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    date: Mapped[PyDate] = mapped_column(Date, nullable=False, index=True)
    # NULL = daily rollup; 0-23 = hourly rollup
    hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    # Sessions that reached MEDIUM or HIGH confidence
    likely_purchases: Mapped[int] = mapped_column(Integer, default=0)
    checkout_visitors: Mapped[int] = mapped_column(Integer, default=0)
    checkout_abandonment: Mapped[int] = mapped_column(Integer, default=0)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    queue_success_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # JSON: {"cash": 12, "card": 30, "upi": 18, "unknown": 40}
    payment_type_distribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    __table_args__ = (
        Index("ix_txn_stat_camera_date_hour", "camera_id", "date", "hour"),
    )
