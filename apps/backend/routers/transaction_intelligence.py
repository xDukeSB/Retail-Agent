"""
transaction_intelligence.py — REST API for the Transaction Intelligence Engine.

All endpoints are local-only, offline-first.
The in-memory TransactionEngine singleton is the source-of-truth for live data.
SQLite is the source-of-truth for historical data.

Mounted at: /api/v1/transactions/intelligence
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.transaction_intelligence import (
    TransactionPrediction,
    TransactionSession,
    TransactionSignal,
    TransactionStatistic,
)
from services.transaction_engine import transaction_engine

logger = logging.getLogger("retailai.routers.txn_intelligence")

router = APIRouter()


# ── Live Sessions ─────────────────────────────────────────────────────────────


@router.get("/sessions/live")
async def get_live_sessions():
    """
    Returns all currently active in-memory transaction sessions.
    Updates in real-time as visitors move through the store.
    Falls back to empty list when no cameras are active.
    """
    sessions = transaction_engine.get_live_sessions()
    return {
        "sessions": sessions,
        "total": len(sessions),
        "at_checkout": sum(
            1 for s in sessions if s["state"] in ("AT_CHECKOUT", "PAYMENT_INTERACTION", "PURCHASE_COMPLETED")
        ),
        "likely_purchases": sum(
            1 for s in sessions if s["confidence_level"] in ("MEDIUM", "HIGH")
        ),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Session History ───────────────────────────────────────────────────────────


@router.get("/sessions")
async def get_sessions(
    camera_id: Optional[str] = None,
    confidence_level: Optional[str] = None,
    target_date: Optional[date] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns completed TransactionSession records from SQLite.
    Useful for historical analysis and cloud dashboard.
    """
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q = (
        select(TransactionSession)
        .where(
            TransactionSession.entered_at >= day_start,
            TransactionSession.entered_at < day_end,
        )
        .order_by(TransactionSession.last_updated.desc())
        .limit(limit)
    )
    if camera_id:
        q = q.where(TransactionSession.camera_id == camera_id)
    if confidence_level:
        q = q.where(TransactionSession.confidence_level == confidence_level)

    result = await db.execute(q)
    sessions = result.scalars().all()

    return {
        "sessions": [
            {
                "id": s.id,
                "track_id": s.track_id,
                "camera_id": s.camera_id,
                "state": s.state,
                "confidence_score": round(s.confidence_score, 1),
                "transaction_probability": round(s.transaction_probability * 100, 1),
                "confidence_level": s.confidence_level,
                "detected_signals": json.loads(s.detected_signals or "[]"),
                "entered_at": s.entered_at.isoformat(),
                "exited_at": s.exited_at.isoformat() if s.exited_at else None,
                "is_complete": s.is_complete,
            }
            for s in sessions
        ],
        "total": len(sessions),
        "date": target_date.isoformat(),
    }


# ── Summary Statistics ────────────────────────────────────────────────────────


@router.get("/stats")
async def get_transaction_stats(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Key transaction KPIs for the dashboard stat cards.
    Reads from TransactionSession history + live sessions.
    """
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    # Historical from DB
    q = select(
        func.count(TransactionSession.id).label("total_sessions"),
        func.avg(TransactionSession.transaction_probability).label("avg_probability"),
    ).where(
        TransactionSession.entered_at >= day_start,
        TransactionSession.entered_at < day_end,
        TransactionSession.is_complete == True,
    )
    if camera_id:
        q = q.where(TransactionSession.camera_id == camera_id)
    result = await db.execute(q)
    row = result.one()

    # Likely purchases from DB
    q2 = select(func.count(TransactionSession.id)).where(
        TransactionSession.entered_at >= day_start,
        TransactionSession.entered_at < day_end,
        TransactionSession.confidence_level.in_(["MEDIUM", "HIGH"]),
        TransactionSession.is_complete == True,
    )
    if camera_id:
        q2 = q2.where(TransactionSession.camera_id == camera_id)
    result2 = await db.execute(q2)
    likely_purchases = result2.scalar() or 0

    # Checkout visitors
    q3 = select(func.count(TransactionSession.id)).where(
        TransactionSession.entered_at >= day_start,
        TransactionSession.entered_at < day_end,
        TransactionSession.state.in_(
            ["AT_CHECKOUT", "PAYMENT_INTERACTION", "PURCHASE_COMPLETED", "EXITED_STORE"]
        ),
        TransactionSession.is_complete == True,
    )
    if camera_id:
        q3 = q3.where(TransactionSession.camera_id == camera_id)
    result3 = await db.execute(q3)
    checkout_visitors = result3.scalar() or 0

    # Payment type distribution (from signals)
    q4 = select(
        TransactionSignal.signal_type,
        func.count(TransactionSignal.id).label("cnt"),
    ).where(
        TransactionSignal.detected_at >= day_start,
        TransactionSignal.detected_at < day_end,
        TransactionSignal.signal_type.in_(
            ["cash_exchange_detected", "card_machine_interaction", "upi_payment_interaction"]
        ),
    ).group_by(TransactionSignal.signal_type)
    result4 = await db.execute(q4)
    payment_rows = result4.all()

    payment_dist = {r[0]: r[1] for r in payment_rows}
    total_payment_signals = sum(payment_dist.values()) or 1

    total_sessions = row.total_sessions or 0
    conversion_rate = (likely_purchases / total_sessions * 100) if total_sessions > 0 else 0.0

    # Add live session counts
    live = transaction_engine.get_live_sessions()
    live_at_checkout = sum(
        1 for s in live
        if s["state"] in ("AT_CHECKOUT", "PAYMENT_INTERACTION", "PURCHASE_COMPLETED")
    )

    return {
        "date": target_date.isoformat(),
        "total_sessions": total_sessions,
        "likely_purchases": likely_purchases,
        "estimated_conversion_rate": round(conversion_rate, 1),
        "checkout_visitors": checkout_visitors,
        "checkout_abandonment": max(0, checkout_visitors - likely_purchases),
        "avg_confidence": round((row.avg_probability or 0) * 100, 1),
        "payment_type_distribution": {
            "cash": payment_dist.get("cash_exchange_detected", 0),
            "card": payment_dist.get("card_machine_interaction", 0),
            "upi": payment_dist.get("upi_payment_interaction", 0),
        },
        "live_at_checkout": live_at_checkout,
        "live_sessions": len(live),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Checkout Funnel ───────────────────────────────────────────────────────────


@router.get("/funnel")
async def get_transaction_funnel(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Transaction-enriched checkout funnel.
    Extends the existing conversion funnel with confidence-based stages.
    """
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    base_q = (
        select(TransactionSession)
        .where(
            TransactionSession.entered_at >= day_start,
            TransactionSession.entered_at < day_end,
            TransactionSession.is_complete == True,
        )
    )
    if camera_id:
        base_q = base_q.where(TransactionSession.camera_id == camera_id)

    result = await db.execute(base_q)
    all_sessions = result.scalars().all()
    total = len(all_sessions)

    shopping = sum(1 for s in all_sessions if s.state not in ("ENTERED_STORE",))
    moving_to_checkout = sum(
        1 for s in all_sessions
        if s.state in ("MOVING_TO_CHECKOUT", "WAITING_IN_QUEUE", "AT_CHECKOUT",
                       "PAYMENT_INTERACTION", "PURCHASE_COMPLETED", "EXITED_STORE")
        and s.confidence_score > 0
    )
    at_checkout = sum(
        1 for s in all_sessions
        if s.state in ("AT_CHECKOUT", "PAYMENT_INTERACTION", "PURCHASE_COMPLETED", "EXITED_STORE")
    )
    payment_interaction = sum(
        1 for s in all_sessions
        if s.state in ("PAYMENT_INTERACTION", "PURCHASE_COMPLETED")
    )
    likely_purchased = sum(
        1 for s in all_sessions
        if s.confidence_level in ("MEDIUM", "HIGH")
    )

    def rate(n):
        return round(n / total * 100, 1) if total > 0 else 0.0

    return {
        "date": target_date.isoformat(),
        "total_entries": total,
        "funnel": [
            {"stage": "Entered Store", "count": total, "rate": 100.0, "color": "#3b82f6"},
            {"stage": "Browsing / Shopping", "count": shopping, "rate": rate(shopping), "color": "#8b5cf6"},
            {"stage": "Moving to Checkout", "count": moving_to_checkout, "rate": rate(moving_to_checkout), "color": "#f59e0b"},
            {"stage": "Reached Checkout", "count": at_checkout, "rate": rate(at_checkout), "color": "#f97316"},
            {"stage": "Payment Interaction", "count": payment_interaction, "rate": rate(payment_interaction), "color": "#ec4899"},
            {"stage": "Likely Purchase", "count": likely_purchased, "rate": rate(likely_purchased), "color": "#10b981"},
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Confidence Distribution ───────────────────────────────────────────────────


@router.get("/distribution")
async def get_confidence_distribution(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Confidence level distribution for all completed sessions today.
    Powers the donut/bar chart in the dashboard.
    """
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q = select(
        TransactionSession.confidence_level,
        func.count(TransactionSession.id).label("cnt"),
        func.avg(TransactionSession.transaction_probability).label("avg_prob"),
    ).where(
        TransactionSession.entered_at >= day_start,
        TransactionSession.entered_at < day_end,
        TransactionSession.is_complete == True,
    ).group_by(TransactionSession.confidence_level)

    if camera_id:
        q = q.where(TransactionSession.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.all()

    dist_map = {r[0]: {"count": r[1], "avg_probability": round((r[2] or 0) * 100, 1)} for r in rows}
    
    levels = [
        {"level": "HIGH", "color": "#10b981", "label": "High Confidence (≥85%)"},
        {"level": "MEDIUM", "color": "#f59e0b", "label": "Medium Confidence (60-85%)"},
        {"level": "LOW", "color": "#f97316", "label": "Low Confidence (35-60%)"},
        {"level": "UNLIKELY", "color": "#6b7280", "label": "Unlikely (<35%)"},
    ]
    total = sum(v["count"] for v in dist_map.values()) or 1

    return {
        "date": target_date.isoformat(),
        "distribution": [
            {
                **lv,
                "count": dist_map.get(lv["level"], {}).get("count", 0),
                "avg_probability": dist_map.get(lv["level"], {}).get("avg_probability", 0),
                "share": round(dist_map.get(lv["level"], {}).get("count", 0) / total * 100, 1),
            }
            for lv in levels
        ],
        "total": total,
    }


# ── Recent Transaction Timeline ───────────────────────────────────────────────


@router.get("/timeline")
async def get_transaction_timeline(
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Recent high-confidence transaction signals — powers the live timeline.
    """
    q = (
        select(TransactionSignal)
        .where(
            TransactionSignal.signal_type.in_(
                ["checkout_zone_entered", "queue_completed", "cash_exchange_detected",
                 "card_machine_interaction", "upi_payment_interaction"]
            )
        )
        .order_by(TransactionSignal.detected_at.desc())
        .limit(limit)
    )
    result = await db.execute(q)
    signals = result.scalars().all()

    SIGNAL_LABELS = {
        "checkout_zone_entered": "Reached Checkout",
        "queue_completed": "Completed Queue",
        "cash_exchange_detected": "Cash Exchange",
        "card_machine_interaction": "Card Payment",
        "upi_payment_interaction": "UPI / QR Payment",
    }
    SIGNAL_ICONS = {
        "checkout_zone_entered": "🛒",
        "queue_completed": "✅",
        "cash_exchange_detected": "💵",
        "card_machine_interaction": "💳",
        "upi_payment_interaction": "📱",
    }

    return {
        "events": [
            {
                "id": s.id,
                "session_id": s.session_id,
                "signal_type": s.signal_type,
                "label": SIGNAL_LABELS.get(s.signal_type, s.signal_type),
                "icon": SIGNAL_ICONS.get(s.signal_type, "•"),
                "score": s.score,
                "zone_name": s.zone_name,
                "detected_at": s.detected_at.isoformat(),
                "metadata": json.loads(s.metadata_json or "{}"),
            }
            for s in signals
        ],
        "total": len(signals),
    }


# ── Queue Metrics ─────────────────────────────────────────────────────────────


@router.get("/queue-metrics")
async def get_queue_metrics(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Queue completion statistics derived from transaction signals.
    """
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q_completed = select(func.count(TransactionSignal.id)).where(
        TransactionSignal.signal_type == "queue_completed",
        TransactionSignal.detected_at >= day_start,
        TransactionSignal.detected_at < day_end,
    )
    q_checkout = select(func.count(TransactionSignal.id)).where(
        TransactionSignal.signal_type == "checkout_zone_entered",
        TransactionSignal.detected_at >= day_start,
        TransactionSignal.detected_at < day_end,
    )

    r1 = await db.execute(q_completed)
    r2 = await db.execute(q_checkout)
    completed = r1.scalar() or 0
    checkout_entries = r2.scalar() or 0

    success_rate = round(completed / checkout_entries * 100, 1) if checkout_entries > 0 else 0.0

    return {
        "date": target_date.isoformat(),
        "queue_completions": completed,
        "checkout_entries": checkout_entries,
        "queue_success_rate": success_rate,
        "queue_abandonment": max(0, checkout_entries - completed),
        "timestamp": datetime.utcnow().isoformat(),
    }
