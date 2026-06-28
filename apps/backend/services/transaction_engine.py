"""
transaction_engine.py — Transaction Intelligence Engine

Sits downstream of the EventEngine. Receives the same detection events
and maintains a per-visitor state machine to estimate purchase likelihood.

INTEGRATION:
    Called from EventEngine._process_event() after the existing
    analytics_tracker.process_frame_detections() call.

ARCHITECTURE:
    1. TransactionSessionState  — in-memory state machine per (camera_id, track_id)
    2. SignalDetector           — observes zone events to fire scored signals
    3. ConfidenceCalculator     — maps cumulative score → probability + level
    4. DB persistence           — async writes to SQLite (never blocks inference)
    5. Cloud sync               — enqueues completed sessions via existing enqueue_sync()

OFFLINE-FIRST:
    All inference and writes are local. Nothing requires internet.
    Cloud sync is handled by the existing CloudSyncService background task.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

from database import AsyncSessionLocal
from models.transaction_intelligence import (
    TransactionPrediction,
    TransactionSession,
    TransactionSignal,
)
from services.cloud_sync import enqueue_sync

logger = logging.getLogger("retailai.transaction_engine")

# ── State Machine ─────────────────────────────────────────────────────────────


class VisitorState(str, Enum):
    ENTERED_STORE = "ENTERED_STORE"
    SHOPPING = "SHOPPING"
    MOVING_TO_CHECKOUT = "MOVING_TO_CHECKOUT"
    WAITING_IN_QUEUE = "WAITING_IN_QUEUE"
    AT_CHECKOUT = "AT_CHECKOUT"
    PAYMENT_INTERACTION = "PAYMENT_INTERACTION"
    PURCHASE_COMPLETED = "PURCHASE_COMPLETED"
    EXITED_STORE = "EXITED_STORE"


# Valid forward transitions
_TRANSITIONS: Dict[VisitorState, List[VisitorState]] = {
    VisitorState.ENTERED_STORE: [VisitorState.SHOPPING, VisitorState.MOVING_TO_CHECKOUT],
    VisitorState.SHOPPING: [VisitorState.MOVING_TO_CHECKOUT, VisitorState.EXITED_STORE],
    VisitorState.MOVING_TO_CHECKOUT: [VisitorState.WAITING_IN_QUEUE, VisitorState.AT_CHECKOUT],
    VisitorState.WAITING_IN_QUEUE: [VisitorState.AT_CHECKOUT],
    VisitorState.AT_CHECKOUT: [VisitorState.PAYMENT_INTERACTION, VisitorState.EXITED_STORE],
    VisitorState.PAYMENT_INTERACTION: [VisitorState.PURCHASE_COMPLETED, VisitorState.EXITED_STORE],
    VisitorState.PURCHASE_COMPLETED: [VisitorState.EXITED_STORE],
    VisitorState.EXITED_STORE: [],
}


# ── Signal Definitions ────────────────────────────────────────────────────────


SIGNAL_SCORES = {
    "checkout_zone_entered": 20,
    "queue_completed": 15,
    "cash_exchange_detected": 25,
    "card_machine_interaction": 25,
    "upi_payment_interaction": 20,
}

MAX_SCORE = sum(SIGNAL_SCORES.values())  # 105


# ── Confidence Levels ─────────────────────────────────────────────────────────


def _compute_confidence(score: float):
    """Returns (probability, level) from raw score."""
    prob = min(score / MAX_SCORE, 1.0)
    if prob >= 0.85:
        level = "HIGH"
    elif prob >= 0.60:
        level = "MEDIUM"
    elif prob >= 0.35:
        level = "LOW"
    else:
        level = "UNLIKELY"
    return prob, level


# ── In-Memory Session State ───────────────────────────────────────────────────


@dataclass
class TransactionSessionState:
    """In-memory state for one visitor's transaction journey."""

    session_id: str
    visitor_uuid: str
    track_id: int
    camera_id: str
    store_id: Optional[str]

    state: VisitorState = VisitorState.ENTERED_STORE
    confidence_score: float = 0.0
    transaction_probability: float = 0.0
    confidence_level: str = "UNLIKELY"
    detected_signals: Set[str] = field(default_factory=set)

    entered_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: float = field(default_factory=time.time)

    # Zone dwell tracking: zone_name → entry timestamp
    zone_entry_times: Dict[str, float] = field(default_factory=dict)
    # Zone visit history (for queue completion detection)
    zones_visited_ordered: List[str] = field(default_factory=list)

    # Throttle: signal_type → last fired time
    signal_cooldowns: Dict[str, float] = field(default_factory=dict)

    # Last confidence_level at which we wrote a Prediction record
    last_persisted_level: str = "UNLIKELY"

    def transition_to(self, new_state: VisitorState) -> bool:
        """Attempt a state transition. Returns True if successful."""
        if new_state in _TRANSITIONS.get(self.state, []):
            logger.debug(
                f"[TXN] Visitor {self.track_id} @ {self.camera_id}: "
                f"{self.state} → {new_state}"
            )
            self.state = new_state
            return True
        return False

    def add_signal(self, signal_type: str) -> bool:
        """
        Records a signal if not already detected and not in cooldown.
        Returns True if signal was newly added.
        """
        if signal_type in self.detected_signals:
            return False  # Already scored this signal

        # 30-second cooldown per signal type (prevents re-firing on brief exits)
        last = self.signal_cooldowns.get(signal_type, 0)
        if time.time() - last < 30:
            return False

        score = SIGNAL_SCORES.get(signal_type, 0)
        self.confidence_score = min(self.confidence_score + score, MAX_SCORE)
        self.detected_signals.add(signal_type)
        self.signal_cooldowns[signal_type] = time.time()
        self.transaction_probability, self.confidence_level = _compute_confidence(
            self.confidence_score
        )
        return True


# ── Zone Name Matchers ────────────────────────────────────────────────────────


def _is_checkout_zone(zone_name: str, zone_type: str) -> bool:
    n = zone_name.lower()
    t = zone_type.lower()
    return t == "checkout" or any(k in n for k in ("checkout", "cashier", "till", "register"))


def _is_queue_zone(zone_name: str, zone_type: str) -> bool:
    n = zone_name.lower()
    t = zone_type.lower()
    return t == "queue" or any(k in n for k in ("queue", "waiting", "line"))


def _is_payment_zone(zone_name: str, zone_type: str) -> bool:
    n = zone_name.lower()
    return any(k in n for k in ("card", "payment", "terminal", "pos", "machine"))


def _is_upi_zone(zone_name: str, zone_type: str) -> bool:
    n = zone_name.lower()
    return any(k in n for k in ("upi", "qr", "phonepe", "gpay", "paytm", "bhim"))


# ── Transaction Engine ────────────────────────────────────────────────────────


class TransactionEngine:
    """
    Per-camera in-memory state machine for transaction intelligence.
    Receives detection frames from EventEngine and emits WebSocket updates.
    """

    def __init__(self):
        # (camera_id, track_id) → TransactionSessionState
        self._sessions: Dict[tuple, TransactionSessionState] = {}
        # Pending DB operations (batch-written)
        self._pending_inserts: List[dict] = []
        self._pending_updates: List[str] = []  # session_ids
        self._last_db_flush = time.time()

    # ── Public API (called by EventEngine) ───────────────────────────────────

    async def process_frame(
        self,
        camera_id: str,
        timestamp: float,
        detections: List[dict],
        zone_crossings: List[dict],  # From AnalyticsTracker's crossing events
    ) -> List[dict]:
        """
        Process one frame's worth of detections and zone events.
        Returns list of transaction update events for WebSocket broadcast.
        """
        events = []
        current_ids = set()

        for det in detections:
            track_id = det.get("track_id")
            if track_id is None or track_id < 0:
                continue

            track_uuid = det.get("db_uuid", "")
            centroid = det.get("centroid", [0.5, 0.5])
            current_ids.add(track_id)

            key = (camera_id, track_id)
            if key not in self._sessions:
                session = self._create_session(
                    track_id, track_uuid, camera_id
                )
                self._sessions[key] = session
                logger.debug(
                    f"[TXN] New session {session.session_id} for track {track_id}"
                )
            else:
                session = self._sessions[key]

            session.last_seen = timestamp

        # Process zone crossings to advance state + fire signals
        for crossing in zone_crossings:
            track_id = crossing.get("track_id")
            key = (camera_id, track_id)
            session = self._sessions.get(key)
            if not session:
                continue

            zone_name = crossing.get("zone_name", "")
            zone_type = crossing.get("zone_type", "general")
            event_type = crossing.get("event_type", "entry")
            ts = crossing.get("timestamp", time.time())
            x = crossing.get("x", 0.5)
            y = crossing.get("y", 0.5)

            signal_fired = await self._handle_zone_crossing(
                session, zone_name, zone_type, event_type, ts, x, y
            )

            if signal_fired or self._state_changed(session):
                ws_event = self._build_ws_event(session)
                events.append(ws_event)

        # Mark visitors not seen for >15s as exited
        await self._handle_lost_tracks(camera_id, timestamp, current_ids)

        # Periodic DB flush
        if time.time() - self._last_db_flush > 5.0:
            await self._flush_to_db()
            self._last_db_flush = time.time()

        return events

    async def notify_track_end(self, camera_id: str, track_id: int, track_uuid: str):
        """Called when AnalyticsTracker marks a track as complete."""
        key = (camera_id, track_id)
        session = self._sessions.pop(key, None)
        if session:
            session.state = VisitorState.EXITED_STORE
            await self._persist_completed_session(session)

    # ── Zone Crossing → Signal + State Logic ─────────────────────────────────

    async def _handle_zone_crossing(
        self,
        session: TransactionSessionState,
        zone_name: str,
        zone_type: str,
        event_type: str,
        ts: float,
        x: float,
        y: float,
    ) -> bool:
        """Translates a zone crossing into a signal + state transition."""
        signal_fired = False

        if event_type == "entry":
            session.zone_entry_times[zone_name] = ts
            if zone_name not in session.zones_visited_ordered:
                session.zones_visited_ordered.append(zone_name)

            # Signal 1: Checkout Zone
            if _is_checkout_zone(zone_name, zone_type):
                if session.add_signal("checkout_zone_entered"):
                    signal_fired = True
                    await self._persist_signal(session, "checkout_zone_entered", zone_name, x, y, ts)
                session.transition_to(VisitorState.AT_CHECKOUT)

            # Signal 4: Card Machine
            if _is_payment_zone(zone_name, zone_type):
                if session.add_signal("card_machine_interaction"):
                    signal_fired = True
                    await self._persist_signal(session, "card_machine_interaction", zone_name, x, y, ts)
                session.transition_to(VisitorState.PAYMENT_INTERACTION)

            # Signal 5: UPI
            if _is_upi_zone(zone_name, zone_type):
                if session.add_signal("upi_payment_interaction"):
                    signal_fired = True
                    await self._persist_signal(session, "upi_payment_interaction", zone_name, x, y, ts)
                session.transition_to(VisitorState.PAYMENT_INTERACTION)

            # Queue zone → state advance
            if _is_queue_zone(zone_name, zone_type):
                session.transition_to(VisitorState.WAITING_IN_QUEUE)

        elif event_type == "exit":
            entry_time = session.zone_entry_times.pop(zone_name, None)
            dwell = (ts - entry_time) if entry_time else 0

            # Signal 2: Queue Completion (exited queue zone after dwell)
            if _is_queue_zone(zone_name, zone_type) and dwell > 20:
                if session.add_signal("queue_completed"):
                    signal_fired = True
                    await self._persist_signal(
                        session, "queue_completed", zone_name, x, y, ts,
                        metadata={"dwell_seconds": round(dwell, 1)}
                    )

            # Signal 3: Cash Exchange Proxy (long dwell at checkout)
            if _is_checkout_zone(zone_name, zone_type) and dwell > 90:
                if session.add_signal("cash_exchange_detected"):
                    signal_fired = True
                    await self._persist_signal(
                        session, "cash_exchange_detected", zone_name, x, y, ts,
                        metadata={"dwell_seconds": round(dwell, 1)}
                    )
                session.transition_to(VisitorState.PURCHASE_COMPLETED)

            # Card/UPI — even brief interaction counts
            if _is_payment_zone(zone_name, zone_type) and dwell > 10:
                if "card_machine_interaction" not in session.detected_signals:
                    if session.add_signal("card_machine_interaction"):
                        signal_fired = True
                        await self._persist_signal(
                            session, "card_machine_interaction", zone_name, x, y, ts,
                            metadata={"dwell_seconds": round(dwell, 1)}
                        )
                session.transition_to(VisitorState.PURCHASE_COMPLETED)

            if _is_upi_zone(zone_name, zone_type) and dwell > 5:
                if "upi_payment_interaction" not in session.detected_signals:
                    if session.add_signal("upi_payment_interaction"):
                        signal_fired = True
                        await self._persist_signal(
                            session, "upi_payment_interaction", zone_name, x, y, ts,
                            metadata={"dwell_seconds": round(dwell, 1)}
                        )
                session.transition_to(VisitorState.PURCHASE_COMPLETED)

        # Write prediction snapshot when confidence level changes
        if signal_fired and session.confidence_level != session.last_persisted_level:
            await self._persist_prediction(session)
            session.last_persisted_level = session.confidence_level

        return signal_fired

    # ── General Movement → State Logic ────────────────────────────────────────

    def _state_changed(self, session: TransactionSessionState) -> bool:
        """Advance ENTERED_STORE → SHOPPING after being seen for 10+ seconds."""
        if session.state == VisitorState.ENTERED_STORE:
            if time.time() - session.entered_at.timestamp() > 10:
                session.transition_to(VisitorState.SHOPPING)
                return True
        return False

    # ── Lost Track Handling ───────────────────────────────────────────────────

    async def _handle_lost_tracks(
        self, camera_id: str, timestamp: float, current_ids: Set[int]
    ):
        lost_keys = [
            key
            for key in list(self._sessions.keys())
            if key[0] == camera_id and key[1] not in current_ids
            and timestamp - self._sessions[key].last_seen > 15.0
        ]
        for key in lost_keys:
            session = self._sessions.pop(key)
            session.state = VisitorState.EXITED_STORE
            await self._persist_completed_session(session)

    # ── DB Persistence ────────────────────────────────────────────────────────

    def _create_session(
        self, track_id: int, visitor_uuid: str, camera_id: str
    ) -> TransactionSessionState:
        return TransactionSessionState(
            session_id=str(uuid.uuid4()),
            visitor_uuid=visitor_uuid or str(uuid.uuid4()),
            track_id=track_id,
            camera_id=camera_id,
            store_id=None,
        )

    async def _persist_signal(
        self,
        session: TransactionSessionState,
        signal_type: str,
        zone_name: str,
        x: float,
        y: float,
        ts: float,
        metadata: Optional[dict] = None,
    ):
        try:
            async with AsyncSessionLocal() as db:
                sig = TransactionSignal(
                    id=str(uuid.uuid4()),
                    session_id=session.session_id,
                    signal_type=signal_type,
                    score=SIGNAL_SCORES.get(signal_type, 0),
                    zone_name=zone_name,
                    detected_at=datetime.fromtimestamp(ts),
                    x=x,
                    y=y,
                    metadata_json=json.dumps(metadata) if metadata else None,
                )
                db.add(sig)
                await db.commit()
                logger.info(
                    f"[TXN] Signal '{signal_type}' for track {session.track_id} "
                    f"(score={sig.score}, zone={zone_name})"
                )
        except Exception as e:
            logger.error(f"[TXN] Failed to persist signal: {e}")

    async def _persist_prediction(self, session: TransactionSessionState):
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.utcnow()
                pred = TransactionPrediction(
                    id=str(uuid.uuid4()),
                    session_id=session.session_id,
                    visitor_uuid=session.visitor_uuid,
                    camera_id=session.camera_id,
                    store_id=session.store_id,
                    transaction_probability=session.transaction_probability,
                    confidence_level=session.confidence_level,
                    detected_signals=json.dumps(list(session.detected_signals)),
                    created_at=now,
                    updated_at=now,
                )
                db.add(pred)

                # Enqueue for cloud sync if MEDIUM or higher
                if session.confidence_level in ("MEDIUM", "HIGH"):
                    enqueue_sync(
                        db,
                        table_name="transaction_predictions",
                        record_id=pred.id,
                        payload={
                            "session_id": session.session_id,
                            "visitor_uuid": session.visitor_uuid,
                            "camera_id": session.camera_id,
                            "transaction_probability": session.transaction_probability,
                            "confidence_level": session.confidence_level,
                            "detected_signals": list(session.detected_signals),
                            "created_at": now.isoformat(),
                        },
                    )

                await db.commit()
        except Exception as e:
            logger.error(f"[TXN] Failed to persist prediction: {e}")

    async def _persist_completed_session(self, session: TransactionSessionState):
        """
        Write or update the TransactionSession record when a visitor exits.
        Also enqueues for cloud sync.
        """
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.utcnow()
                existing = await db.get(TransactionSession, session.session_id)

                if existing:
                    existing.state = session.state.value
                    existing.confidence_score = session.confidence_score
                    existing.transaction_probability = session.transaction_probability
                    existing.confidence_level = session.confidence_level
                    existing.detected_signals = json.dumps(list(session.detected_signals))
                    existing.exited_at = now
                    existing.last_updated = now
                    existing.is_complete = True
                else:
                    txn_session = TransactionSession(
                        id=session.session_id,
                        visitor_uuid=session.visitor_uuid,
                        track_id=session.track_id,
                        camera_id=session.camera_id,
                        store_id=session.store_id,
                        state=session.state.value,
                        confidence_score=session.confidence_score,
                        transaction_probability=session.transaction_probability,
                        confidence_level=session.confidence_level,
                        detected_signals=json.dumps(list(session.detected_signals)),
                        entered_at=session.entered_at,
                        exited_at=now,
                        last_updated=now,
                        is_complete=True,
                    )
                    db.add(txn_session)

                # Enqueue session for cloud sync regardless of confidence
                enqueue_sync(
                    db,
                    table_name="transaction_sessions",
                    record_id=session.session_id,
                    payload={
                        "session_id": session.session_id,
                        "camera_id": session.camera_id,
                        "state": session.state.value,
                        "confidence_level": session.confidence_level,
                        "transaction_probability": session.transaction_probability,
                        "detected_signals": list(session.detected_signals),
                        "entered_at": session.entered_at.isoformat(),
                        "exited_at": now.isoformat(),
                    },
                )
                await db.commit()
                logger.info(
                    f"[TXN] Session {session.session_id} completed: "
                    f"{session.confidence_level} ({session.transaction_probability:.2%})"
                )
        except Exception as e:
            logger.error(f"[TXN] Failed to persist session: {e}")

    async def _flush_to_db(self):
        """Upsert all active (incomplete) sessions to DB for crash-safety."""
        sessions_snapshot = list(self._sessions.values())
        if not sessions_snapshot:
            return
        try:
            async with AsyncSessionLocal() as db:
                for session in sessions_snapshot:
                    existing = await db.get(TransactionSession, session.session_id)
                    now = datetime.utcnow()
                    if existing:
                        existing.state = session.state.value
                        existing.confidence_score = session.confidence_score
                        existing.transaction_probability = session.transaction_probability
                        existing.confidence_level = session.confidence_level
                        existing.detected_signals = json.dumps(list(session.detected_signals))
                        existing.last_updated = now
                    else:
                        txn_session = TransactionSession(
                            id=session.session_id,
                            visitor_uuid=session.visitor_uuid,
                            track_id=session.track_id,
                            camera_id=session.camera_id,
                            store_id=session.store_id,
                            state=session.state.value,
                            confidence_score=session.confidence_score,
                            transaction_probability=session.transaction_probability,
                            confidence_level=session.confidence_level,
                            detected_signals=json.dumps(list(session.detected_signals)),
                            entered_at=session.entered_at,
                            last_updated=now,
                            is_complete=False,
                        )
                        db.add(txn_session)
                await db.commit()
        except Exception as e:
            logger.error(f"[TXN] Periodic flush error: {e}")

    # ── WebSocket Event Builder ───────────────────────────────────────────────

    def _build_ws_event(self, session: TransactionSessionState) -> dict:
        return {
            "type": "transaction_update",
            "session_id": session.session_id,
            "track_id": session.track_id,
            "camera_id": session.camera_id,
            "state": session.state.value,
            "confidence_score": round(session.confidence_score, 1),
            "transaction_probability": round(session.transaction_probability, 4),
            "confidence_level": session.confidence_level,
            "detected_signals": list(session.detected_signals),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ── Live Session Snapshot (for API) ──────────────────────────────────────

    def get_live_sessions(self) -> List[dict]:
        """Returns all currently active in-memory sessions for the live view."""
        return [
            {
                "session_id": s.session_id,
                "track_id": s.track_id,
                "camera_id": s.camera_id,
                "state": s.state.value,
                "confidence_score": round(s.confidence_score, 1),
                "transaction_probability": round(s.transaction_probability * 100, 1),
                "confidence_level": s.confidence_level,
                "detected_signals": list(s.detected_signals),
                "entered_at": s.entered_at.isoformat(),
                "dwell_seconds": round(time.time() - s.entered_at.timestamp(), 0),
            }
            for s in self._sessions.values()
        ]


# Singleton — imported by EventEngine
transaction_engine = TransactionEngine()
