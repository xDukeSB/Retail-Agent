"""
Aggregator service — runs as a background task on the backend.
Every minute it computes hourly and daily rollups from raw track/event data.
This is what makes all dashboard queries fast (pre-aggregated).
"""
import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from config import settings
from database import AsyncSessionLocal
from models.analytics import DailyReport, HourlyCount
from models.track import PersonTrack

logger = logging.getLogger("retailai.aggregator")


class AggregatorService:
    def __init__(self):
        self.interval = settings.AGGREGATION_INTERVAL_SECONDS

    async def run_loop(self):
        """Runs the aggregation loop every N seconds."""
        logger.info(f"Aggregator started — interval: {self.interval}s")
        while True:
            try:
                await self.aggregate_current_hour()
                await self.aggregate_today()
            except asyncio.CancelledError:
                logger.info("Aggregator cancelled")
                return
            except Exception as e:
                logger.error(f"Aggregator error: {e}", exc_info=True)
            await asyncio.sleep(self.interval)

    async def aggregate_current_hour(self):
        """Computes the HourlyCount for the current hour across all cameras."""
        now = datetime.utcnow()
        hour_start = now.replace(minute=0, second=0, microsecond=0)

        async with AsyncSessionLocal() as db:
            # Get all distinct camera_ids with tracks in this hour
            q = select(PersonTrack.camera_id).where(
                PersonTrack.entry_time >= hour_start,
                PersonTrack.entry_time < hour_start + timedelta(hours=1),
            ).distinct()
            result = await db.execute(q)
            camera_ids = [r[0] for r in result.all()]

            for camera_id in camera_ids:
                await self._compute_hourly(db, camera_id, hour_start)
            await db.commit()

    async def _compute_hourly(self, db, camera_id: str, hour_start: datetime):
        """Computes or updates a single HourlyCount row."""
        hour_end = hour_start + timedelta(hours=1)

        q = select(
            func.count(PersonTrack.id).label("total"),
            func.avg(PersonTrack.dwell_seconds).label("avg_dwell"),
            func.max(PersonTrack.dwell_seconds).label("max_dwell"),
        ).where(
            PersonTrack.camera_id == camera_id,
            PersonTrack.entry_time >= hour_start,
            PersonTrack.entry_time < hour_end,
        )
        result = await db.execute(q)
        row = result.one()

        # Count entries (tracks starting in this hour)
        entries_q = select(func.count(PersonTrack.id)).where(
            PersonTrack.camera_id == camera_id,
            PersonTrack.entry_time >= hour_start,
            PersonTrack.entry_time < hour_end,
        )
        entries_result = await db.execute(entries_q)
        entries = entries_result.scalar() or 0

        # Count exits (tracks ending in this hour)
        exits_q = select(func.count(PersonTrack.id)).where(
            PersonTrack.camera_id == camera_id,
            PersonTrack.exit_time >= hour_start,
            PersonTrack.exit_time < hour_end,
            PersonTrack.is_complete == True,
        )
        exits_result = await db.execute(exits_q)
        exits = exits_result.scalar() or 0

        # Find existing hourly record
        existing_q = select(HourlyCount).where(
            HourlyCount.camera_id == camera_id,
            HourlyCount.hour == hour_start,
        )
        existing_result = await db.execute(existing_q)
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.entries = entries
            existing.exits = exits
            existing.total_tracks = row.total or 0
            existing.avg_dwell_seconds = float(row.avg_dwell or 0)
            existing.max_dwell_seconds = float(row.max_dwell or 0)
            existing.computed_at = datetime.utcnow()
        else:
            db.add(HourlyCount(
                id=str(uuid.uuid4()),
                camera_id=camera_id,
                hour=hour_start,
                entries=entries,
                exits=exits,
                peak_count=entries,  # simplified
                total_tracks=row.total or 0,
                avg_dwell_seconds=float(row.avg_dwell or 0),
                max_dwell_seconds=float(row.max_dwell or 0),
                computed_at=datetime.utcnow(),
            ))

    async def aggregate_today(self):
        """Computes or updates the DailyReport for today."""
        today = date.today()

        async with AsyncSessionLocal() as db:
            # Get all cameras with data today
            q = select(PersonTrack.camera_id).where(
                PersonTrack.date == today,
            ).distinct()
            result = await db.execute(q)
            camera_ids = [r[0] for r in result.all()]

            for camera_id in camera_ids:
                await self._compute_daily(db, camera_id, today)

            # Also compute store-wide (camera_id=None)
            await self._compute_daily(db, None, today)
            await db.commit()

    async def _compute_daily(self, db, camera_id, target_date: date):
        """Computes or updates a single DailyReport row."""
        # Count entries (tracks starting today)
        entries_q = select(func.count(PersonTrack.id)).where(
            PersonTrack.date == target_date
        )
        if camera_id:
            entries_q = entries_q.where(PersonTrack.camera_id == camera_id)
        entries_result = await db.execute(entries_q)
        total_entries = entries_result.scalar() or 0

        # Count exits (tracks that completed today)
        exits_q = select(func.count(PersonTrack.id)).where(
            PersonTrack.date == target_date,
            PersonTrack.is_complete == True,
        )
        if camera_id:
            exits_q = exits_q.where(PersonTrack.camera_id == camera_id)
        exits_result = await db.execute(exits_q)
        total_exits = exits_result.scalar() or 0

        # Average dwell from completed tracks
        avg_dwell_q = select(func.avg(PersonTrack.dwell_seconds)).where(
            PersonTrack.date == target_date,
            PersonTrack.is_complete == True,
        )
        if camera_id:
            avg_dwell_q = avg_dwell_q.where(PersonTrack.camera_id == camera_id)
        avg_dwell_result = await db.execute(avg_dwell_q)
        avg_dwell = float(avg_dwell_result.scalar() or 0)

        # Find peak hour
        peak_q = (
            select(
                func.strftime("%H", PersonTrack.entry_time).label("hour"),
                func.count(PersonTrack.id).label("cnt"),
            )
            .where(PersonTrack.date == target_date)
            .group_by(func.strftime("%H", PersonTrack.entry_time))
            .order_by(func.count(PersonTrack.id).desc())
            .limit(1)
        )
        if camera_id:
            peak_q = peak_q.where(PersonTrack.camera_id == camera_id)
        peak_result = await db.execute(peak_q)
        peak_row = peak_result.first()
        peak_hour = int(peak_row[0]) if peak_row else None
        peak_count = int(peak_row[1]) if peak_row else 0

        # Upsert daily report
        existing_q = select(DailyReport).where(DailyReport.date == target_date)
        if camera_id:
            existing_q = existing_q.where(DailyReport.camera_id == camera_id)
        else:
            existing_q = existing_q.where(DailyReport.camera_id.is_(None))

        existing_result = await db.execute(existing_q)
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.total_entries = total_entries
            existing.total_exits = total_exits
            existing.unique_visitors = total_entries
            existing.avg_dwell_seconds = avg_dwell
            existing.peak_hour = peak_hour
            existing.peak_count = peak_count
            existing.computed_at = datetime.utcnow()
        else:
            db.add(DailyReport(
                id=str(uuid.uuid4()),
                camera_id=camera_id,
                date=target_date,
                total_entries=total_entries,
                total_exits=total_exits,
                unique_visitors=total_entries,
                avg_dwell_seconds=avg_dwell,
                peak_hour=peak_hour,
                peak_count=peak_count,
                computed_at=datetime.utcnow(),
            ))
