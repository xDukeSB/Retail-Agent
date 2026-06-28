"""
analytics.py — Dwell Time Analytics Endpoints
"""
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from app.core.deps import get_current_active_user
from app.models.user import User
from app.services.analytics_service import analytics_service
from app.services.zone_analytics_service import zone_analytics_service
from app.services.dashboard_service import dashboard_service
from app.db.checkout_repository import checkout_repository
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dwell-time", response_model=Dict[str, Any])
async def get_dwell_time_report(
    camera_id: str,
    since_ts: float = Query(default_factory=lambda: time.time() - 86400),
    until_ts: Optional[float] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get dwell time statistics for a specific camera in a time range.
    By default, since_ts is 24 hours ago.
    """
    report = await analytics_service.get_dwell_time_report(
        camera_id=camera_id,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    return report

@router.get("/zones", response_model=Dict[str, Any])
async def get_zone_analytics_report(
    camera_id: str,
    since_ts: float = Query(default_factory=lambda: time.time() - 86400),
    until_ts: Optional[float] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get zone statistics for a specific camera in a time range.
    By default, since_ts is 24 hours ago.
    """
    report = await zone_analytics_service.get_zone_analytics_report(
        camera_id=camera_id,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    return report

@router.get("/summary", response_model=Dict[str, Any])
async def get_dashboard_summary(
    camera_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return await dashboard_service.get_summary(camera_id, date_from, date_to)

@router.get("/traffic/hourly", response_model=list)
async def get_hourly_traffic(
    camera_id: Optional[str] = None,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return await dashboard_service.get_hourly_traffic(camera_id, target_date)

@router.get("/traffic/daily", response_model=list)
async def get_daily_traffic(
    days: int = 30,
    camera_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return await dashboard_service.get_daily_traffic(days, camera_id)

@router.get("/conversion", response_model=Dict[str, Any])
async def get_conversion(
    camera_id: Optional[str] = None,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return await dashboard_service.get_conversion_metrics(camera_id, target_date)

@router.get("/queue", response_model=Dict[str, Any])
async def get_queue(
    camera_id: Optional[str] = None,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return await dashboard_service.get_queue_metrics(camera_id, target_date)

@router.get("/dwell", response_model=Dict[str, Any])
async def get_dwell(
    camera_id: Optional[str] = None,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    # Map target_date to since_ts/until_ts for analytics_service
    import datetime
    since_ts = time.time() - 86400
    until_ts = None
    if target_date:
        try:
            dt = datetime.datetime.fromisoformat(target_date)
            since_ts = dt.replace(hour=0, minute=0, second=0).timestamp()
            until_ts = since_ts + 86400
        except ValueError:
            pass
    # Get dwell report from analytics service
    if camera_id is None:
        # Fallback to getting all logic if needed, but currently requires camera_id
        # we will use an empty string to return 0s if no camera_id provided since it requires one
        camera_id = ""
    
    # Actually, let's make camera_id optional in analytics_service if possible, 
    # but for now, we'll try to fetch or return empty
    if not camera_id:
        return {"avg_dwell_seconds": 0, "median_dwell_seconds": 0, "distribution": []}

    report = await analytics_service.get_dwell_time_report(camera_id, since_ts, until_ts)
    return report.get("statistics", {})

@router.get("/checkout/metrics", response_model=Dict[str, Any])
async def get_checkout_metrics(
    camera_id: Optional[str] = None,
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get overall checkout metrics."""
    import datetime
    since_ts = time.time() - 86400
    until_ts = None
    if target_date:
        try:
            dt = datetime.datetime.fromisoformat(target_date)
            since_ts = dt.replace(hour=0, minute=0, second=0).timestamp()
            until_ts = since_ts + 86400
        except ValueError:
            pass
            
    async with AsyncSessionLocal() as session:
        return await checkout_repository.get_metrics(session, camera_id, since_ts, until_ts)

@router.get("/checkout/sessions", response_model=list)
async def get_checkout_sessions(
    camera_id: Optional[str] = None,
    target_date: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get list of individual checkout sessions."""
    import datetime
    since_ts = time.time() - 86400
    until_ts = None
    if target_date:
        try:
            dt = datetime.datetime.fromisoformat(target_date)
            since_ts = dt.replace(hour=0, minute=0, second=0).timestamp()
            until_ts = since_ts + 86400
        except ValueError:
            pass
            
    async with AsyncSessionLocal() as session:
        sessions = await checkout_repository.get_sessions(session, camera_id, since_ts, until_ts, limit, offset)
        return [s.to_dict() for s in sessions]
