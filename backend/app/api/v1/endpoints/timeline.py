"""
timeline.py — REST endpoint for querying historical timeline events.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from app.core.deps import get_current_active_user
from app.models.user import User
from app.db.session import AsyncSessionLocal
from app.db.timeline_repository import timeline_repository

router = APIRouter(prefix="/timeline", tags=["Timeline"])

@router.get("", response_model=Dict[str, Any])
async def get_timeline_events(
    start_ts: Optional[float] = Query(None, description="Start timestamp (Unix)"),
    end_ts: Optional[float] = Query(None, description="End timestamp (Unix)"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get paginated, historical timeline events with optional filtering.
    """
    types_list = [t.strip() for t in event_types.split(",")] if event_types else None
    
    async with AsyncSessionLocal() as session:
        events = await timeline_repository.get_events(
            session=session,
            start_ts=start_ts,
            end_ts=end_ts,
            camera_id=camera_id,
            event_types=types_list,
            limit=limit,
            offset=offset
        )
        
    return {
        "data": [e.to_dict() for e in events],
        "limit": limit,
        "offset": offset,
        "count": len(events)
    }
