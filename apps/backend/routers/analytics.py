"""
Analytics router — serves all dashboard metrics.
All queries are local SQLite — works 100% offline.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.analytics import DailyReport, HeatmapCell, HourlyCount, QueueSnapshot
from models.track import PersonTrack

router = APIRouter()


# ── Overview / Summary ────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    camera_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Top-level KPIs: total entries, unique visitors, avg dwell, peak hour."""
    if not date_from:
        date_from = date.today()
    if not date_to:
        date_to = date.today()

    q = select(
        func.sum(DailyReport.total_entries).label("total_entries"),
        func.sum(DailyReport.total_exits).label("total_exits"),
        func.sum(DailyReport.unique_visitors).label("unique_visitors"),
        func.avg(DailyReport.avg_dwell_seconds).label("avg_dwell"),
        func.max(DailyReport.peak_count).label("peak_count"),
    ).where(
        DailyReport.date >= date_from,
        DailyReport.date <= date_to,
    )
    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    row = result.one()

    return {
        "total_entries": row.total_entries or 0,
        "total_exits": row.total_exits or 0,
        "unique_visitors": row.unique_visitors or 0,
        "avg_dwell_seconds": round(row.avg_dwell or 0, 1),
        "peak_count": row.peak_count or 0,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }


# ── Traffic Trends ────────────────────────────────────────────────────────────

@router.get("/traffic/hourly")
async def get_hourly_traffic(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Hourly entry/exit counts for a given day — powers the main traffic chart."""
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q = select(HourlyCount).where(
        HourlyCount.hour >= day_start,
        HourlyCount.hour < day_end,
    ).order_by(HourlyCount.hour)

    if camera_id:
        q = q.where(HourlyCount.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    return [
        {
            "hour": r.hour.strftime("%H:%M"),
            "hour_ts": r.hour.isoformat(),
            "entries": r.entries,
            "exits": r.exits,
            "peak_count": r.peak_count,
            "avg_dwell_seconds": round(r.avg_dwell_seconds, 1),
            "camera_id": r.camera_id,
        }
        for r in rows
    ]


@router.get("/traffic/daily")
async def get_daily_traffic(
    camera_id: Optional[str] = None,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Daily traffic for the past N days — powers the trend charts."""
    date_from = date.today() - timedelta(days=days - 1)

    q = select(DailyReport).where(DailyReport.date >= date_from).order_by(DailyReport.date)
    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    return [
        {
            "date": r.date.isoformat(),
            "total_entries": r.total_entries,
            "total_exits": r.total_exits,
            "unique_visitors": r.unique_visitors,
            "avg_dwell_seconds": round(r.avg_dwell_seconds, 1),
            "peak_hour": r.peak_hour,
            "peak_count": r.peak_count,
            "camera_id": r.camera_id,
        }
        for r in rows
    ]


# ── Dwell Time ────────────────────────────────────────────────────────────────

@router.get("/dwell")
async def get_dwell_distribution(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Distribution of dwell times — how long visitors stay."""
    if not target_date:
        target_date = date.today()

    q = select(PersonTrack.dwell_seconds).where(
        PersonTrack.date == target_date,
        PersonTrack.is_complete == True,
        PersonTrack.dwell_seconds.isnot(None),
    )
    if camera_id:
        q = q.where(PersonTrack.camera_id == camera_id)

    result = await db.execute(q)
    dwells = [r[0] for r in result.all() if r[0] is not None]

    # Bucket into ranges
    buckets = {
        "0-30s": 0, "30-60s": 0, "1-2m": 0,
        "2-5m": 0, "5-10m": 0, "10m+": 0,
    }
    for d in dwells:
        if d < 30:
            buckets["0-30s"] += 1
        elif d < 60:
            buckets["30-60s"] += 1
        elif d < 120:
            buckets["1-2m"] += 1
        elif d < 300:
            buckets["2-5m"] += 1
        elif d < 600:
            buckets["5-10m"] += 1
        else:
            buckets["10m+"] += 1

    return {
        "distribution": [{"range": k, "count": v} for k, v in buckets.items()],
        "avg_dwell_seconds": round(sum(dwells) / len(dwells), 1) if dwells else 0,
        "median_dwell_seconds": round(sorted(dwells)[len(dwells) // 2], 1) if dwells else 0,
        "total_tracks": len(dwells),
    }


# ── Heatmap ───────────────────────────────────────────────────────────────────

@router.get("/heatmap")
async def get_heatmap(
    camera_id: str,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Heatmap grid data for a camera on a given date."""
    if not target_date:
        target_date = date.today()

    q = select(HeatmapCell).where(
        HeatmapCell.camera_id == camera_id,
        HeatmapCell.date == target_date,
    )
    result = await db.execute(q)
    cells = result.scalars().all()

    max_density = max((c.density for c in cells), default=1.0)

    return {
        "camera_id": camera_id,
        "date": target_date.isoformat(),
        "grid_size": 100,
        "max_density": max_density,
        "cells": [
            {
                "x": c.cell_x,
                "y": c.cell_y,
                "density": c.density,
                "normalized": round(c.density / max_density, 3) if max_density > 0 else 0,
                "visits": c.visit_count,
            }
            for c in cells
        ],
    }


# ── Zones Distribution ────────────────────────────────────────────────────────

@router.get("/zones")
async def get_zone_distribution(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Zone distribution: visits and average dwell per zone."""
    import json
    if not target_date:
        target_date = date.today()

    q = select(PersonTrack.zones_visited, PersonTrack.dwell_seconds).where(
        PersonTrack.date == target_date,
        PersonTrack.is_complete == True,
        PersonTrack.zones_visited.isnot(None),
    )
    if camera_id:
        q = q.where(PersonTrack.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.all()
    
    zone_stats = {}
    total_visits = 0
    
    for row in rows:
        zones_visited_str, dwell = row
        if not zones_visited_str: continue
        try:
            zones = json.loads(zones_visited_str)
            # Dedup zones for a single person's track
            for zone in set(zones):
                if zone not in zone_stats:
                    zone_stats[zone] = {"visits": 0, "dwells": []}
                zone_stats[zone]["visits"] += 1
                if dwell:
                    zone_stats[zone]["dwells"].append(dwell)
                total_visits += 1
        except:
            pass

    zone_dist = []
    # Assign some consistent colors for known zones
    colors = {"Entrance": "#10b981", "Drinks": "#0ea5e9", "Snacks": "#84cc16", "Checkout": "#f59e0b", "Produce": "#3b82f6", "Cosmetics": "#d946ef"}
    default_colors = ["#10b981", "#0ea5e9", "#84cc16", "#f59e0b", "#3b82f6", "#d946ef", "#6366f1", "#ec4899", "#8b5cf6", "#14b8a6"]
    
    sorted_zones = sorted(zone_stats.items(), key=lambda x: x[1]["visits"], reverse=True)
    for i, (z_name, stats) in enumerate(sorted_zones):
        avg_dwell = sum(stats["dwells"]) / len(stats["dwells"]) if stats["dwells"] else 0
        zone_dist.append({
            "name": z_name,
            "value": stats["visits"],
            "avg_dwell_seconds": avg_dwell,
            "fill": colors.get(z_name, default_colors[i % len(default_colors)])
        })
        
    return {
        "date": target_date.isoformat(),
        "total_zone_visits": total_visits,
        "zones": zone_dist
    }


# ── Queue Analytics ───────────────────────────────────────────────────────────

@router.get("/queue")
async def get_queue_analytics(
    camera_id: Optional[str] = None,
    zone_name: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Queue depth and wait times over a day."""
    if not target_date:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q = select(QueueSnapshot).where(
        QueueSnapshot.timestamp >= day_start,
        QueueSnapshot.timestamp < day_end,
    ).order_by(QueueSnapshot.timestamp)

    if camera_id:
        q = q.where(QueueSnapshot.camera_id == camera_id)
    if zone_name:
        q = q.where(QueueSnapshot.zone_name == zone_name)

    result = await db.execute(q)
    snapshots = result.scalars().all()

    return {
        "camera_id": camera_id,
        "zone_name": zone_name,
        "date": target_date.isoformat(),
        "snapshots": [
            {
                "time": s.timestamp.strftime("%H:%M"),
                "timestamp": s.timestamp.isoformat(),
                "queue_depth": s.queue_depth,
                "avg_wait_seconds": s.avg_wait_seconds,
                "max_wait_seconds": s.max_wait_seconds,
                "zone_name": s.zone_name,
            }
            for s in snapshots
        ],
        "avg_queue_depth": round(
            sum(s.queue_depth for s in snapshots) / len(snapshots), 1
        ) if snapshots else 0,
        "peak_queue": max((s.queue_depth for s in snapshots), default=0),
    }


# ── Conversion Funnel ─────────────────────────────────────────────────────────

@router.get("/conversion")
async def get_conversion_funnel(
    camera_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Conversion funnel: entries → zone visits → checkout."""
    if not target_date:
        target_date = date.today()

    q = select(
        func.count(PersonTrack.id).label("total"),
        func.count(PersonTrack.id).filter(PersonTrack.zones_visited.isnot(None)).label("browsed"),
    ).where(
        PersonTrack.date == target_date,
        PersonTrack.is_complete == True,
    )
    if camera_id:
        q = q.where(PersonTrack.camera_id == camera_id)

    result = await db.execute(q)
    row = result.one()
    total = row.total or 0
    browsed = row.browsed or 0

    # Approximate checkout from queue snapshots
    q2 = select(func.count(QueueSnapshot.id)).where(
        func.date(QueueSnapshot.timestamp) == target_date,
    )
    if camera_id:
        q2 = q2.where(QueueSnapshot.camera_id == camera_id)
    checkout_result = await db.execute(q2)
    checkout_visits = min(checkout_result.scalar() or 0, browsed)

    return {
        "date": target_date.isoformat(),
        "funnel": [
            {"stage": "Entered Store", "count": total, "rate": 100.0},
            {
                "stage": "Browsed (Visited Zone)",
                "count": browsed,
                "rate": round(browsed / total * 100, 1) if total > 0 else 0,
            },
            {
                "stage": "Reached Checkout",
                "count": checkout_visits,
                "rate": round(checkout_visits / total * 100, 1) if total > 0 else 0,
            },
        ],
    }


# ── Live Counts ───────────────────────────────────────────────────────────────

@router.get("/live")
async def get_live_counts(
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Current in-store count (entries - exits today)."""
    today = date.today()

    q = select(
        func.sum(DailyReport.total_entries).label("entries"),
        func.sum(DailyReport.total_exits).label("exits"),
    ).where(DailyReport.date == today)

    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    row = result.one()
    entries = row.entries or 0
    exits = row.exits or 0

    return {
        "current_in_store": max(0, entries - exits),
        "today_entries": entries,
        "today_exits": exits,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Conversion Trend ──────────────────────────────────────────────────────────

@router.get("/conversion-trend")
async def get_conversion_trend(
    camera_id: Optional[str] = None,
    days: int = Query(default=7, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Daily conversion rate % over the past N days — powers the trend chart."""
    date_from = date.today() - timedelta(days=days - 1)

    q = select(DailyReport).where(DailyReport.date >= date_from).order_by(DailyReport.date)
    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    daily_rows = result.scalars().all()

    trend = []
    for r in daily_rows:
        total = r.total_entries or 0
        # Approximate checkout: unique visitors who reached checkout
        # Use conversion_rate if stored, otherwise derive from unique_visitors
        rate = round(r.conversion_rate * 100, 1) if r.conversion_rate else (
            round(r.unique_visitors / total * 100, 1) if total > 0 else 0
        )
        trend.append({
            "date": r.date.isoformat(),
            "day": r.date.strftime("%a"),
            "conversion_rate": rate,
            "total_entries": total,
            "unique_visitors": r.unique_visitors,
        })

    return {
        "days": days,
        "trend": trend,
    }

