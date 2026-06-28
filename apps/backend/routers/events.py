"""
Events router — ingests raw CV pipeline events and serves the live event feed.
This is the bridge between the CV pipeline and the analytics engine.
"""
import json
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.event import ZoneEvent
from models.track import PersonTrack
from routers.websocket import broadcast_event

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TrackStartEvent(BaseModel):
    camera_id: str
    session_track_id: int
    timestamp: datetime
    x: float
    y: float

class TrackUpdateEvent(BaseModel):
    camera_id: str
    session_track_id: int
    timestamp: datetime
    x: float
    y: float
    zone_name: Optional[str] = None

class TrackEndEvent(BaseModel):
    camera_id: str
    session_track_id: int
    entry_time: datetime
    exit_time: datetime
    dwell_seconds: float
    zones_visited: List[str]
    path_json: List[List[float]]  # [[x, y, ts], ...]

class ZoneCrossingEvent(BaseModel):
    camera_id: str
    session_track_id: int
    zone_name: str
    zone_type: str
    event_type: str  # entry | exit | dwell_start | dwell_end
    timestamp: datetime
    x: float
    y: float

class QueueEvent(BaseModel):
    camera_id: str
    zone_name: str
    queue_depth: int
    avg_wait_seconds: Optional[float]
    max_wait_seconds: Optional[float]
    timestamp: datetime

class HeatmapBatch(BaseModel):
    camera_id: str
    date: date
    cells: List[dict]  # [{x, y, density, visits}]


# In-memory store for active tracks (keyed by camera_id + session_track_id)
_active_tracks: dict = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/track/start")
async def track_start(event: TrackStartEvent, db: AsyncSession = Depends(get_db)):
    """CV pipeline calls this when a new person enters the frame."""
    key = f"{event.camera_id}:{event.session_track_id}"
    track = PersonTrack(
        id=str(uuid.uuid4()),
        camera_id=event.camera_id,
        session_track_id=event.session_track_id,
        entry_time=event.timestamp,
        date=event.timestamp.date(),
        is_complete=False,
    )
    db.add(track)
    await db.flush()
    _active_tracks[key] = track.id

    await broadcast_event({
        "type": "track_start",
        "camera_id": event.camera_id,
        "track_id": track.id,
        "timestamp": event.timestamp.isoformat(),
        "x": event.x,
        "y": event.y,
    })
    return {"track_id": track.id}


@router.post("/track/end")
async def track_end(event: TrackEndEvent, db: AsyncSession = Depends(get_db)):
    """CV pipeline calls this when a person leaves the frame."""
    key = f"{event.camera_id}:{event.session_track_id}"
    track_id = _active_tracks.get(key)

    if track_id:
        track = await db.get(PersonTrack, track_id)
        if track:
            track.exit_time = event.exit_time
            track.dwell_seconds = event.dwell_seconds
            track.zones_visited = json.dumps(event.zones_visited)
            track.path_json = json.dumps(event.path_json)
            track.is_complete = True
            await db.flush()
        _active_tracks.pop(key, None)

    await broadcast_event({
        "type": "track_end",
        "camera_id": event.camera_id,
        "dwell_seconds": event.dwell_seconds,
        "zones_visited": event.zones_visited,
        "timestamp": event.exit_time.isoformat(),
    })
    return {"status": "ok"}


@router.post("/zone-crossing")
async def zone_crossing(event: ZoneCrossingEvent, db: AsyncSession = Depends(get_db)):
    """CV pipeline calls this when a tracked person crosses a zone boundary."""
    key = f"{event.camera_id}:{event.session_track_id}"
    track_id = _active_tracks.get(key, "unknown")

    zone_event = ZoneEvent(
        id=str(uuid.uuid4()),
        track_id=track_id,
        camera_id=event.camera_id,
        zone_name=event.zone_name,
        zone_type=event.zone_type,
        event_type=event.event_type,
        timestamp=event.timestamp,
        x=event.x,
        y=event.y,
    )
    db.add(zone_event)
    await db.flush()

    await broadcast_event({
        "type": "zone_crossing",
        "camera_id": event.camera_id,
        "zone_name": event.zone_name,
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat(),
    })
    return {"status": "ok"}


@router.post("/queue")
async def queue_snapshot(event: QueueEvent, db: AsyncSession = Depends(get_db)):
    """CV pipeline reports queue depth every ~30 seconds."""
    from models.analytics import QueueSnapshot
    snapshot = QueueSnapshot(
        id=str(uuid.uuid4()),
        camera_id=event.camera_id,
        zone_name=event.zone_name,
        timestamp=event.timestamp,
        queue_depth=event.queue_depth,
        avg_wait_seconds=event.avg_wait_seconds,
        max_wait_seconds=event.max_wait_seconds,
    )
    db.add(snapshot)
    await db.flush()

    await broadcast_event({
        "type": "queue_update",
        "camera_id": event.camera_id,
        "zone_name": event.zone_name,
        "queue_depth": event.queue_depth,
        "avg_wait_seconds": event.avg_wait_seconds,
        "timestamp": event.timestamp.isoformat(),
    })
    return {"status": "ok"}


@router.post("/heatmap/batch")
async def heatmap_batch(batch: HeatmapBatch, db: AsyncSession = Depends(get_db)):
    """CV pipeline pushes heatmap cell updates in bulk every few minutes."""
    from models.analytics import HeatmapCell
    from sqlalchemy import select, and_

    for cell_data in batch.cells:
        q = select(HeatmapCell).where(
            and_(
                HeatmapCell.camera_id == batch.camera_id,
                HeatmapCell.date == batch.date,
                HeatmapCell.cell_x == cell_data["x"],
                HeatmapCell.cell_y == cell_data["y"],
            )
        )
        result = await db.execute(q)
        existing = result.scalar_one_or_none()

        if existing:
            existing.density += cell_data.get("density", 0)
            existing.visit_count += cell_data.get("visits", 0)
            existing.updated_at = datetime.utcnow()
        else:
            db.add(HeatmapCell(
                id=str(uuid.uuid4()),
                camera_id=batch.camera_id,
                date=batch.date,
                cell_x=cell_data["x"],
                cell_y=cell_data["y"],
                density=cell_data.get("density", 0),
                visit_count=cell_data.get("visits", 0),
                updated_at=datetime.utcnow(),
            ))

    await db.flush()
    return {"status": "ok", "cells_updated": len(batch.cells)}


@router.get("/history")
async def get_history(
    limit: int = 50,
    offset: int = 0,
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Fetch unified history of events."""
    from sqlalchemy import select, desc
    
    events = []
    
    # 1. Get PersonTracks (Entry and Exit)
    q_tracks = select(PersonTrack).order_by(desc(PersonTrack.entry_time)).limit(limit).offset(offset)
    if camera_id:
        q_tracks = q_tracks.where(PersonTrack.camera_id == camera_id)
    tracks_result = await db.execute(q_tracks)
    for t in tracks_result.scalars().all():
        events.append({
            "id": f"entry_{t.id}",
            "type": "entry",
            "track_id": t.id,
            "camera_id": t.camera_id,
            "timestamp": t.entry_time.isoformat(),
            "zone_name": "Main Entrance",
            "dwell_seconds": None
        })
        if t.is_complete and t.exit_time:
            events.append({
                "id": f"exit_{t.id}",
                "type": "exit",
                "track_id": t.id,
                "camera_id": t.camera_id,
                "timestamp": t.exit_time.isoformat(),
                "zone_name": "Main Entrance",
                "dwell_seconds": t.dwell_seconds
            })

    # 2. Get Zone Events
    q_zones = select(ZoneEvent).order_by(desc(ZoneEvent.timestamp)).limit(limit).offset(offset)
    if camera_id:
        q_zones = q_zones.where(ZoneEvent.camera_id == camera_id)
    zones_result = await db.execute(q_zones)
    for z in zones_result.scalars().all():
        events.append({
            "id": f"zone_{z.id}",
            "type": "zone",
            "track_id": z.track_id,
            "camera_id": z.camera_id,
            "timestamp": z.timestamp.isoformat(),
            "zone_name": z.zone_name,
            "event_type": z.event_type
        })

    # 3. Get Queue Snapshots (where depth > 0)
    from models.analytics import QueueSnapshot
    q_queues = select(QueueSnapshot).where(QueueSnapshot.queue_depth > 0).order_by(desc(QueueSnapshot.timestamp)).limit(limit).offset(offset)
    if camera_id:
        q_queues = q_queues.where(QueueSnapshot.camera_id == camera_id)
    queues_result = await db.execute(q_queues)
    for q in queues_result.scalars().all():
        events.append({
            "id": f"queue_{q.id}",
            "type": "queue_update",
            "track_id": None,
            "camera_id": q.camera_id,
            "timestamp": q.timestamp.isoformat(),
            "zone_name": q.zone_name,
            "queue_depth": q.queue_depth,
            "avg_wait_seconds": q.avg_wait_seconds
        })

    # Sort combined events by timestamp descending
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Return paginated slice
    return events[:limit]
