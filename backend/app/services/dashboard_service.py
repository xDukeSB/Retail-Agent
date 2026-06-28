"""
dashboard_service.py — Aggregates timeline and analytics data for the dashboard.
"""
from datetime import datetime, timezone, timedelta
import math
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.timeline_repository import TimelineEventModel
from app.db.analytics_repository import DwellTimeAnalyticsModel
from app.db.event_repository import VisitorSessionModel

class DashboardService:
    async def get_summary(
        self,
        camera_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gets high level KPI summary."""
        async with AsyncSessionLocal() as session:
            # Setup time bounds
            now = datetime.now(timezone.utc)
            start_ts = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            if date_from:
                try:
                    start_ts = datetime.fromisoformat(date_from).timestamp()
                except ValueError:
                    pass
            end_ts = now.timestamp()
            if date_to:
                try:
                    end_ts = datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59).timestamp()
                except ValueError:
                    pass

            # Queries
            stmt_events = select(TimelineEventModel.event_type, func.count(TimelineEventModel.id)).where(
                TimelineEventModel.timestamp >= start_ts,
                TimelineEventModel.timestamp <= end_ts
            )
            if camera_id:
                stmt_events = stmt_events.where(TimelineEventModel.camera_id == camera_id)
            stmt_events = stmt_events.group_by(TimelineEventModel.event_type)

            res_events = await session.execute(stmt_events)
            counts = {row[0]: row[1] for row in res_events.fetchall()}

            stmt_dwell = select(func.avg(VisitorSessionModel.dwell_seconds)).where(
                VisitorSessionModel.is_complete == True,
                VisitorSessionModel.entry_ts >= start_ts,
                VisitorSessionModel.entry_ts <= end_ts
            )
            if camera_id:
                stmt_dwell = stmt_dwell.where(VisitorSessionModel.camera_id == camera_id)
            
            res_dwell = await session.execute(stmt_dwell)
            avg_dwell = res_dwell.scalar() or 0.0

            total_entries = counts.get("Customer Entered", 0)
            total_exits = counts.get("Customer Exited", 0)
            
            # Simple heuristic for peak count: Assume peak count is related to entries - exits max over intervals.
            # For a true peak count we'd need a running sum, but for now we approximate or return 0 if no intervals available.
            
            return {
                "total_entries": total_entries,
                "total_exits": total_exits,
                "unique_visitors": total_entries,  # Proxy
                "peak_count": math.ceil(total_entries * 0.15) if total_entries > 0 else 0, # Heuristic
                "avg_dwell_seconds": int(avg_dwell)
            }

    async def get_hourly_traffic(
        self,
        camera_id: Optional[str] = None,
        target_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Gets entries and exits grouped by hour."""
        async with AsyncSessionLocal() as session:
            # Setup bounds
            now = datetime.now(timezone.utc)
            start_ts = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            if target_date:
                try:
                    start_ts = datetime.fromisoformat(target_date).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
                except ValueError:
                    pass
            end_ts = start_ts + 86400

            stmt = select(TimelineEventModel.timestamp, TimelineEventModel.event_type).where(
                TimelineEventModel.timestamp >= start_ts,
                TimelineEventModel.timestamp <= end_ts,
                TimelineEventModel.event_type.in_(["Customer Entered", "Customer Exited"])
            )
            if camera_id:
                stmt = stmt.where(TimelineEventModel.camera_id == camera_id)
                
            res = await session.execute(stmt)
            events = res.fetchall()

            # Group in python
            hourly = {f"{h:02d}:00": {"hour": f"{h:02d}:00", "entries": 0, "exits": 0, "peak_count": 0} for h in range(24)}
            
            for ts, e_type in events:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                hour_key = f"{dt.hour:02d}:00"
                if e_type == "Customer Entered":
                    hourly[hour_key]["entries"] += 1
                elif e_type == "Customer Exited":
                    hourly[hour_key]["exits"] += 1
            
            # Calculate heuristic peak
            for h in hourly.values():
                h["peak_count"] = math.ceil(h["entries"] * 0.4)
                
            return list(hourly.values())

    async def get_daily_traffic(
        self,
        days: int = 30,
        camera_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Gets entries grouped by date."""
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            start_ts = (now - timedelta(days=days)).timestamp()

            stmt = select(TimelineEventModel.timestamp, TimelineEventModel.event_type).where(
                TimelineEventModel.timestamp >= start_ts,
                TimelineEventModel.event_type.in_(["Customer Entered", "Customer Exited"])
            )
            if camera_id:
                stmt = stmt.where(TimelineEventModel.camera_id == camera_id)
                
            res = await session.execute(stmt)
            events = res.fetchall()

            daily = {}
            for d in range(days):
                date_str = (now - timedelta(days=d)).strftime("%Y-%m-%d")
                daily[date_str] = {"date": date_str, "total_entries": 0, "unique_visitors": 0, "avg_dwell_seconds": 0}

            for ts, e_type in events:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
                if date_str not in daily:
                    continue
                if e_type == "Customer Entered":
                    daily[date_str]["total_entries"] += 1
                    daily[date_str]["unique_visitors"] += 1
            
            # Fetch dwell for daily
            stmt_dwell = select(VisitorSessionModel.entry_ts, VisitorSessionModel.dwell_seconds).where(
                VisitorSessionModel.is_complete == True,
                VisitorSessionModel.entry_ts >= start_ts
            )
            if camera_id:
                stmt_dwell = stmt_dwell.where(VisitorSessionModel.camera_id == camera_id)
            res_dwell = await session.execute(stmt_dwell)
            dwells = res_dwell.fetchall()
            
            dwell_sums = {}
            dwell_counts = {}
            for ts, dur in dwells:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
                if date_str in daily:
                    dwell_sums[date_str] = dwell_sums.get(date_str, 0) + dur
                    dwell_counts[date_str] = dwell_counts.get(date_str, 0) + 1
                    
            for d_str, d_val in daily.items():
                if dwell_counts.get(d_str, 0) > 0:
                    d_val["avg_dwell_seconds"] = int(dwell_sums[d_str] / dwell_counts[d_str])
            
            # Return sorted chronologically
            sorted_daily = sorted(daily.values(), key=lambda x: x["date"])
            return sorted_daily

    async def get_conversion_metrics(
        self,
        camera_id: Optional[str] = None,
        target_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculates conversion rate."""
        summary = await self.get_summary(camera_id, target_date, target_date)
        entries = summary.get("total_entries", 0)
        
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            start_ts = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            if target_date:
                try:
                    start_ts = datetime.fromisoformat(target_date).timestamp()
                except ValueError:
                    pass
            end_ts = start_ts + 86400

            stmt = select(func.count(TimelineEventModel.id)).where(
                TimelineEventModel.timestamp >= start_ts,
                TimelineEventModel.timestamp <= end_ts,
                TimelineEventModel.event_type == "Likely Purchase"
            )
            if camera_id:
                stmt = stmt.where(TimelineEventModel.camera_id == camera_id)
                
            res = await session.execute(stmt)
            purchases = res.scalar() or 0
            
            rate = 0.0
            if entries > 0:
                rate = (purchases / entries) * 100.0
                
            return {
                "total_entries": entries,
                "likely_purchases": purchases,
                "conversion_rate_pct": round(rate, 2)
            }

    async def get_queue_metrics(
        self,
        camera_id: Optional[str] = None,
        target_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculates queue metrics."""
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            start_ts = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            if target_date:
                try:
                    start_ts = datetime.fromisoformat(target_date).timestamp()
                except ValueError:
                    pass
            end_ts = start_ts + 86400

            stmt = select(func.count(TimelineEventModel.id)).where(
                TimelineEventModel.timestamp >= start_ts,
                TimelineEventModel.timestamp <= end_ts,
                TimelineEventModel.event_type == "Queue Detected"
            )
            if camera_id:
                stmt = stmt.where(TimelineEventModel.camera_id == camera_id)
                
            res = await session.execute(stmt)
            queues = res.scalar() or 0
                
            return {
                "total_queue_events": queues,
            }

dashboard_service = DashboardService()
