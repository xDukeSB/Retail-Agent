"""
analytics_service.py — Orchestrates Dwell Time Analytics Engine.
"""
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.analytics_repository import analytics_repository
from app.db.event_repository import VisitorSessionModel
from app.db.session import AsyncSessionLocal
from app.services.dwell_time_calculator import calculate_statistics

logger = get_logger(__name__)


class AnalyticsService:
    """Service layer for dwell time analytics."""

    async def process_completed_visit(
        self,
        camera_id: str,
        visitor_id: int,
        entry_ts: float,
        exit_ts: float,
        duration_seconds: float,
    ) -> None:
        """
        Save the completed session duration to the analytics table.
        Called in real-time when a visitor exits.
        """
        async with AsyncSessionLocal() as session:
            try:
                await analytics_repository.save_dwell_time_record(
                    session=session,
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    entry_ts=entry_ts,
                    exit_ts=exit_ts,
                    duration_seconds=duration_seconds,
                )
                await session.commit()
                logger.info(
                    "Dwell time analytics recorded",
                    extra={
                        "camera_id": camera_id,
                        "visitor_id": visitor_id,
                        "duration_seconds": round(duration_seconds, 1),
                    }
                )
            except Exception as e:
                await session.rollback()
                logger.error("Failed to record dwell time analytics", exc_info=e)

    async def get_dwell_time_report(
        self,
        camera_id: str,
        since_ts: float,
        until_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Fetch records and calculate math statistics."""
        async with AsyncSessionLocal() as session:
            stmt = select(VisitorSessionModel.dwell_seconds).where(
                VisitorSessionModel.camera_id == camera_id,
                VisitorSessionModel.is_complete == True,
                VisitorSessionModel.exit_ts >= since_ts
            )
            if until_ts:
                stmt = stmt.where(VisitorSessionModel.exit_ts <= until_ts)
                
            result = await session.execute(stmt)
            durations = [r for r in result.scalars().all() if r is not None]
            stats = calculate_statistics(durations)
            
            return {
                "camera_id": camera_id,
                "since_ts": since_ts,
                "until_ts": until_ts,
                "statistics": stats,
            }


# Singleton service
analytics_service = AnalyticsService()
