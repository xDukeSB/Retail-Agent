"""
event_service.py — Entry/Exit Event orchestrator.

Connects:
  TrackingPipeline (TrackedVisitor frames + VisitorEvents)
      ↓
  LineCrossingDetector (virtual line geometry)
      ↓
  EventRepository (SQLite persistence)
      ↓
  WebSocket broadcaster (real-time push)

Responsibilities:
  1. Load persisted lines from DB on startup and register with detector
  2. Subscribe to TrackingPipeline for tracking frames + visitor lifecycle events
  3. On each tracking frame → run LineCrossingDetector.process_frame()
  4. On crossing → persist CrossingEvent, upsert VisitorSession, broadcast
  5. On VisitorEvent.EXIT → close open VisitorSession
  6. Expose FastAPI router: lines CRUD, events query, sessions, summary
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Awaitable
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import require_permission
from app.core.logging import get_logger
from app.db.event_repository import (
    CrossingEventModel, EntryExitLineModel, VisitorSessionModel,
    event_repository,
)
from app.db.session import AsyncSessionLocal
from app.services.line_crossing import (
    LineCrossing, LineCrossingDetector, LineType, VirtualLine,
    CrossingEventType, line_crossing_detector,
)
from app.services.tracking_models import TrackingFrame, VisitorEvent, VisitorEventType
from app.services.analytics_service import analytics_service
from app.services.timeline_service import timeline_service

logger = get_logger(__name__)


# ── Pydantic request/response schemas ──────────────────────────────────────────

class LineCreateRequest(BaseModel):
    camera_id:      str
    name:           str   = Field(default="Entry/Exit Line", max_length=100)
    line_type:      str   = Field(default="both", pattern="^(entry|exit|both)$")
    x1:             float = Field(ge=0.0, le=1.0)
    y1:             float = Field(ge=0.0, le=1.0)
    x2:             float = Field(ge=0.0, le=1.0)
    y2:             float = Field(ge=0.0, le=1.0)
    flip_direction: bool  = False
    is_active:      bool  = True
    min_crossings:  int   = Field(default=1, ge=1, le=5)

    model_config = {"json_schema_extra": {
        "example": {
            "camera_id":     "cam-uuid-1234",
            "name":          "Main Entrance",
            "line_type":     "entry",
            "x1": 0.1, "y1": 0.5,
            "x2": 0.4, "y2": 0.5,
            "flip_direction": False,
        }
    }}


class LineUpdateRequest(BaseModel):
    name:           Optional[str]  = None
    line_type:      Optional[str]  = Field(default=None, pattern="^(entry|exit|both)$")
    x1:             Optional[float] = Field(default=None, ge=0.0, le=1.0)
    y1:             Optional[float] = Field(default=None, ge=0.0, le=1.0)
    x2:             Optional[float] = Field(default=None, ge=0.0, le=1.0)
    y2:             Optional[float] = Field(default=None, ge=0.0, le=1.0)
    flip_direction: Optional[bool]  = None
    is_active:      Optional[bool]  = None
    min_crossings:  Optional[int]   = Field(default=None, ge=1, le=5)


# ── Event Metrics ─────────────────────────────────────────────────────────────

class EventMetrics:
    def __init__(self):
        self.frames_processed   = 0
        self.total_crossings    = 0
        self.customer_entries   = 0
        self.customer_exits     = 0
        self.db_write_errors    = 0
        self.broadcast_count    = 0

    def to_dict(self) -> dict:
        return {
            "frames_processed": self.frames_processed,
            "total_crossings":  self.total_crossings,
            "customer_entries": self.customer_entries,
            "customer_exits":   self.customer_exits,
            "db_write_errors":  self.db_write_errors,
            "broadcast_count":  self.broadcast_count,
        }


# ── Event Service ─────────────────────────────────────────────────────────────

class EventService:
    """
    Central orchestrator for the entry/exit event pipeline.
    One instance per application lifetime (singleton).
    """

    def __init__(
        self,
        detector: Optional[LineCrossingDetector] = None,
    ):
        self._detector    = detector or line_crossing_detector
        self._repo        = event_repository
        self._running     = False
        self.metrics      = EventMetrics()
        self._tasks:      list[asyncio.Task] = []
        # Broadcast callbacks: async (event_dict) → None
        self._broadcast_cbs: list[Callable[[dict], Awaitable[None]]] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, tracking_pipeline) -> None:
        """
        Start event service:
          1. Load all persisted lines from DB and register with detector
          2. Subscribe to tracking pipeline frames and visitor events
        """
        if self._running:
            return
        self._running = True

        # Restore lines from DB
        await self._load_lines_from_db()

        # Subscribe to tracking pipeline
        tracking_pipeline.add_tracking_callback(self._on_tracking_frame)
        tracking_pipeline.add_event_callback(self._on_visitor_event)

        self._tasks = [
            asyncio.create_task(self._metrics_log_loop(), name="event-metrics"),
        ]
        logger.info("EventService started")

    async def stop(self, tracking_pipeline) -> None:
        if not self._running:
            return
        self._running = False
        tracking_pipeline.remove_tracking_callback(self._on_tracking_frame)
        tracking_pipeline.remove_event_callback(self._on_visitor_event)
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("EventService stopped", extra={"metrics": self.metrics.to_dict()})

    # ── Broadcast subscription ─────────────────────────────────────────────────

    def add_broadcast_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        self._broadcast_cbs.append(cb)

    def remove_broadcast_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        self._broadcast_cbs = [c for c in self._broadcast_cbs if c is not cb]

    # ── Line management (public, called by API) ────────────────────────────────

    async def create_line(self, data: dict) -> dict:
        """Create a line, persist it, and register with detector."""
        line_id = data.get("id", str(uuid.uuid4()))
        data["id"] = line_id

        async with AsyncSessionLocal() as session:
            async with session.begin():
                model = await self._repo.create_line(session, data)

        # Register with in-memory detector
        vline = VirtualLine.from_dict({**data, "id": line_id})
        self._detector.add_line(vline)
        logger.info("Line created", extra={"line_id": line_id, "camera_id": data["camera_id"]})
        return model.to_dict()

    async def update_line(self, line_id: str, updates: dict) -> Optional[dict]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                model = await self._repo.update_line(session, line_id, updates)
                if not model:
                    return None
                result = model.to_dict()

        # Sync detector — rebuild VirtualLine from updated DB model
        updated_vline = VirtualLine.from_dict(result)
        self._detector.update_line(updated_vline)
        return result

    async def delete_line(self, line_id: str, camera_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                deleted = await self._repo.delete_line(session, line_id)

        if deleted:
            self._detector.remove_line(camera_id, line_id)
        return deleted

    async def get_camera_lines(self, camera_id: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            models = await self._repo.get_lines_for_camera(session, camera_id, active_only=False)
            return [m.to_dict() for m in models]

    # ── Query APIs ────────────────────────────────────────────────────────────

    async def get_crossings(
        self,
        camera_id: Optional[str] = None,
        event_type: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        async with AsyncSessionLocal() as session:
            events = await self._repo.get_crossings(
                session,
                camera_id=camera_id,
                event_type=event_type,
                since_ts=since_ts,
                limit=limit,
                offset=offset,
            )
            return [e.to_dict() for e in events]

    async def get_sessions(
        self,
        camera_id: Optional[str] = None,
        complete_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        async with AsyncSessionLocal() as session:
            sessions = await self._repo.get_sessions(
                session,
                camera_id=camera_id,
                complete_only=complete_only,
                limit=limit,
                offset=offset,
            )
            return [s.to_dict() for s in sessions]

    async def get_summary(self, camera_id: str) -> dict:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        async with AsyncSessionLocal() as session:
            return await self._repo.get_summary(session, camera_id, since_ts=today_start)

    def get_status(self) -> dict:
        return {
            "running":   self._running,
            "metrics":   self.metrics.to_dict(),
            "detector":  self._detector.get_status(),
        }

    # ── Internal pipeline handlers ─────────────────────────────────────────────

    async def _on_tracking_frame(self, frame: TrackingFrame) -> None:
        """Called for every tracked frame — detect line crossings."""
        if not self._running:
            return
        self.metrics.frames_processed += 1

        crossings = self._detector.process_frame(
            camera_id=frame.camera_id,
            visitors=frame.tracked,
            timestamp=frame.timestamp,
        )

        if not crossings:
            return

        for crossing in crossings:
            self.metrics.total_crossings += 1
            if crossing.event_type == CrossingEventType.CUSTOMER_ENTERED:
                self.metrics.customer_entries += 1
            else:
                self.metrics.customer_exits += 1

            # Persist and broadcast (fire-and-forget task)
            asyncio.create_task(
                self._persist_and_broadcast(crossing),
                name=f"crossing-{crossing.visitor_id}",
            )

    async def _on_visitor_event(self, event: VisitorEvent) -> None:
        """Called for ENTER/EXIT/REACQUIRED visitor lifecycle events."""
        if not self._running:
            return
        # On EXIT — close any open session for this visitor
        if event.event_type == VisitorEventType.EXIT:
            asyncio.create_task(
                self._close_session_on_track_removal(event),
                name=f"close-session-{event.visitor_id}",
            )
            # Clean up detector state for removed visitor
            self._detector.purge_visitor(event.camera_id, event.visitor_id)

    async def _persist_and_broadcast(self, crossing: LineCrossing) -> None:
        """Write crossing to DB, upsert session, broadcast via WS."""
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    # 1. Persist raw crossing event
                    event_model = await self._repo.record_crossing(session, crossing)

                    # 2. Upsert visitor session
                    vs = await self._repo.create_or_get_session(
                        session,
                        camera_id=crossing.camera_id,
                        visitor_id=crossing.visitor_id,
                        visitor_label=crossing.visitor_label,
                    )

                    if crossing.event_type == CrossingEventType.CUSTOMER_ENTERED:
                        await self._repo.record_entry(
                            session, vs,
                            crossing_event_id=event_model.id,
                            entry_ts=crossing.timestamp,
                            line_id=crossing.line_id,
                            confidence=crossing.confidence,
                        )
                    else:
                        await self._repo.record_exit(
                            session, vs,
                            crossing_event_id=event_model.id,
                            exit_ts=crossing.timestamp,
                            line_id=crossing.line_id,
                            confidence=crossing.confidence,
                        )

            # 3. Broadcast
            payload = {
                "type":    "crossing_event",
                "payload": crossing.to_dict(),
            }
            await self._broadcast(payload)
            self.metrics.broadcast_count += 1

            # 4. Timeline Event
            event_type = "Customer Entered" if crossing.event_type == CrossingEventType.CUSTOMER_ENTERED else "Customer Exited"
            await timeline_service.log_event(
                event_type=event_type,
                camera_id=crossing.camera_id,
                timestamp=crossing.timestamp,
                visitor_id=crossing.visitor_id,
                details={"line_id": crossing.line_id, "confidence": crossing.confidence}
            )

        except Exception as exc:
            self.metrics.db_write_errors += 1
            logger.error(
                "Crossing persist error",
                extra={"visitor_id": crossing.visitor_id, "error": str(exc)},
            )

    async def _close_session_on_track_removal(self, event: VisitorEvent) -> None:
        """When a track is fully REMOVED, finalise any open session."""
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    vs = await self._repo.create_or_get_session(
                        session,
                        camera_id=event.camera_id,
                        visitor_id=event.visitor_id,
                        visitor_label=event.visitor_label,
                    )
                    if vs.entry_ts and not vs.exit_ts:
                        vs.exit_ts        = event.timestamp
                        vs.is_complete    = True
                        vs.dwell_seconds  = event.timestamp - vs.entry_ts
                        
                        # Process analytics immediately
                        asyncio.create_task(
                            analytics_service.process_completed_visit(
                                camera_id=event.camera_id,
                                visitor_id=event.visitor_id,
                                entry_ts=vs.entry_ts,
                                exit_ts=vs.exit_ts,
                                duration_seconds=vs.dwell_seconds
                            ),
                            name=f"dwell-analytics-{event.visitor_id}"
                        )
            logger.info(
                "Session closed on track removal",
                extra={
                    "visitor_id": event.visitor_id,
                    "camera_id":  event.camera_id,
                },
            )
        except Exception as exc:
            logger.error("Session close error", extra={"error": str(exc)})

    async def _broadcast(self, payload: dict) -> None:
        for cb in list(self._broadcast_cbs):
            try:
                await cb(payload)
            except Exception as exc:
                logger.error("Event broadcast error", extra={"error": str(exc)})

    async def _load_lines_from_db(self) -> None:
        """Restore detector state from persisted lines on startup."""
        try:
            async with AsyncSessionLocal() as session:
                models = await self._repo.get_all_active_lines(session)
                count = 0
                for m in models:
                    try:
                        vline = VirtualLine.from_dict(m.to_dict())
                        self._detector.add_line(vline)
                        count += 1
                    except Exception as exc:
                        logger.warning(
                            "Skipping invalid line",
                            extra={"line_id": m.id, "error": str(exc)},
                        )
            logger.info("Lines restored from DB", extra={"count": count})
        except Exception as exc:
            logger.error("Failed to load lines from DB", extra={"error": str(exc)})

    async def _metrics_log_loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            logger.info("EventService metrics", extra=self.metrics.to_dict())


# ── Singleton ─────────────────────────────────────────────────────────────────

_event_service_instance: Optional[EventService] = None


def get_event_service() -> EventService:
    global _event_service_instance
    if _event_service_instance is None:
        _event_service_instance = EventService()
    return _event_service_instance


# ── REST API Router ───────────────────────────────────────────────────────────

event_router = APIRouter(prefix="/events", tags=["Events"])


# -- Lines endpoints -----------------------------------------------------------

@event_router.post("/lines", status_code=201, summary="Draw a virtual entry/exit line")
async def create_line(
    body: LineCreateRequest,
    _: None = Depends(require_permission("cameras:write")),
):
    """
    Draw a virtual line on a camera frame.
    x1,y1 → x2,y2 are normalized [0,1] coordinates.
    """
    try:
        result = await get_event_service().create_line(body.model_dump())
        return {"success": True, "line": result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@event_router.get(
    "/lines/{camera_id}",
    summary="List all virtual lines for a camera",
)
async def list_lines(
    camera_id: str,
    _: None = Depends(require_permission("cameras:read")),
):
    lines = await get_event_service().get_camera_lines(camera_id)
    return {"camera_id": camera_id, "lines": lines, "count": len(lines)}


@event_router.patch(
    "/lines/{line_id}",
    summary="Update a virtual line definition",
)
async def update_line(
    line_id: str,
    body: LineUpdateRequest,
    _: None = Depends(require_permission("cameras:write")),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result  = await get_event_service().update_line(line_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Line not found")
    return {"success": True, "line": result}


@event_router.delete(
    "/lines/{camera_id}/{line_id}",
    summary="Remove a virtual line",
)
async def delete_line(
    camera_id: str,
    line_id:   str,
    _: None = Depends(require_permission("cameras:write")),
):
    deleted = await get_event_service().delete_line(line_id, camera_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Line not found")
    return {"success": True, "line_id": line_id}


# -- Crossing events endpoints -------------------------------------------------

@event_router.get(
    "/crossings",
    summary="List crossing events (paginated)",
)
async def list_crossings(
    camera_id:  Optional[str]   = Query(default=None),
    event_type: Optional[str]   = Query(default=None, pattern="^(customer_entered|customer_exited)$"),
    since_ts:   Optional[float] = Query(default=None, description="Unix timestamp lower bound"),
    limit:      int             = Query(default=50, ge=1, le=500),
    offset:     int             = Query(default=0, ge=0),
    _: None = Depends(require_permission("analytics:read")),
):
    events = await get_event_service().get_crossings(
        camera_id=camera_id,
        event_type=event_type,
        since_ts=since_ts,
        limit=limit,
        offset=offset,
    )
    return {"events": events, "count": len(events), "offset": offset}


# -- Sessions endpoints --------------------------------------------------------

@event_router.get(
    "/sessions",
    summary="List visitor sessions with entry/exit times",
)
async def list_sessions(
    camera_id:     Optional[str] = Query(default=None),
    complete_only: bool          = Query(default=False, description="Only show complete sessions"),
    limit:         int           = Query(default=50, ge=1, le=500),
    offset:        int           = Query(default=0, ge=0),
    _: None = Depends(require_permission("analytics:read")),
):
    sessions = await get_event_service().get_sessions(
        camera_id=camera_id,
        complete_only=complete_only,
        limit=limit,
        offset=offset,
    )
    return {"sessions": sessions, "count": len(sessions), "offset": offset}


# -- Summary endpoint ----------------------------------------------------------

@event_router.get(
    "/summary/{camera_id}",
    summary="Today's entry/exit counts and occupancy for a camera",
)
async def get_summary(
    camera_id: str,
    _: None = Depends(require_permission("analytics:read")),
):
    return await get_event_service().get_summary(camera_id)


# -- Status endpoint -----------------------------------------------------------

@event_router.get(
    "/status",
    summary="Event service health and metrics",
)
async def event_status(
    _: None = Depends(require_permission("cameras:read")),
):
    return get_event_service().get_status()
