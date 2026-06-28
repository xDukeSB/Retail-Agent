"""
tracking_pipeline.py — Connects DetectionPipeline → ByteTrack → downstream.

Data flow:
  DetectionPipeline ──→ TrackingPipeline ──→ AnalyticsPipeline
       DetectionFrame         TrackingFrame     VisitorEvents
                              VisitorEvents
                                   │
                                   └──→ WebSocket /ws/live
                                   └──→ DB writer (counts, dwell)

Features:
  - Subscribes to DetectionPipeline as a DetectionCallback
  - Runs TrackingService.process() in thread executor (scipy/numpy blocking)
  - Emits TrackingFrame + VisitorEvent to registered subscribers
  - Handles camera add/remove lifecycle
  - Exposes /tracking/status and /tracking/cameras/{id} REST endpoints
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends

from app.core.deps import require_permission
from app.core.logging import get_logger
from app.services.detection_models import DetectionFrame
from app.services.tracking_models import TrackingFrame, VisitorEvent
from app.services.tracking_service import TrackingService, tracking_service

logger = get_logger(__name__)

# Callback types
TrackingCallback = Callable[[TrackingFrame], Awaitable[None]]
EventCallback    = Callable[[VisitorEvent], Awaitable[None]]


# ── Metrics ───────────────────────────────────────────────────────────────────

class TrackingMetrics:
    def __init__(self):
        self.frames_processed = 0
        self.total_events     = 0
        self.enter_events     = 0
        self.exit_events      = 0
        self.errors           = 0
        self._latencies: list[float] = []

    def record(self, ms: float, events: int) -> None:
        self.frames_processed += 1
        self.total_events     += events
        self._latencies.append(ms)
        if len(self._latencies) > 200:
            self._latencies.pop(0)

    @property
    def avg_latency_ms(self) -> float:
        return sum(self._latencies) / len(self._latencies) if self._latencies else 0.0

    def to_dict(self) -> dict:
        return {
            "frames_processed": self.frames_processed,
            "total_events":     self.total_events,
            "enter_events":     self.enter_events,
            "exit_events":      self.exit_events,
            "avg_latency_ms":   round(self.avg_latency_ms, 2),
            "errors":           self.errors,
        }


# ── Tracking Pipeline ─────────────────────────────────────────────────────────

class TrackingPipeline:
    """
    Subscribes to EngineManager (Multiprocessing CV Pipeline)
    and emits TrackingFrame + VisitorEvent to downstream.
    """

    def __init__(self, service: TrackingService | None = None):
        self._svc              = service or tracking_service
        self._running          = False
        self._track_callbacks: list[TrackingCallback] = []
        self._event_callbacks: list[EventCallback]    = []
        self.metrics           = TrackingMetrics()
        self._tasks:           list[asyncio.Task]     = []
        self._latest_frame:    dict[str, TrackingFrame] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("TrackingPipeline started (Bridging EngineManager).")

        from inference_engine.engine_manager import engine_manager
        
        async def _consume_loop():
            while self._running:
                try:
                    event = await engine_manager.get_next_event()
                    await self._process_engine_event(event)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"TrackingPipeline consume error: {e}")
                    await asyncio.sleep(0.1)

        task = asyncio.create_task(_consume_loop())
        self._tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("TrackingPipeline stopped.")

    # ── Subscriptions ─────────────────────────────────────────────────────────

    def subscribe_tracking(self, callback: TrackingCallback) -> None:
        self._track_callbacks.append(callback)

    def subscribe_events(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    # ── Processing ────────────────────────────────────────────────────────────

    async def _process_engine_event(self, event: dict) -> None:
        """Converts raw YOLO/ByteTrack dict into TrackingFrame and emits."""
        t0 = time.time()
        
        cam_id = event["camera_id"]
        ts = event["timestamp"]
        raw_detections = event.get("detections", [])
        
        # Build TrackingFrame
        frame = TrackingFrame(camera_id=cam_id, timestamp=ts, tracked_objects=[])
        
        events_emitted = 0
        
        # We still need to run the line crossing logic (which TrackingService handles)
        from app.services.tracking_models import TrackedObject
        
        for det in raw_detections:
            obj = TrackedObject(
                track_id=det["track_id"],
                label="person",
                confidence=det["confidence"],
                bbox=det["bbox"],
                centroid=tuple(det["centroid"]),
                velocity=(0.0, 0.0), # Optional calculation
                history=[]
            )
            frame.tracked_objects.append(obj)
            
        self._latest_frame[cam_id] = frame
        
        try:
            # We bypass the NaiveTracker (it was in tracking_service.process previously)
            # and just pass the pre-tracked frame to generate visitor events.
            visitor_events = await self._svc.process_pretracked(frame)
            events_emitted = len(visitor_events)
            
            # Broadcast
            for cb in self._track_callbacks:
                await cb(frame)
            for ev in visitor_events:
                for cb in self._event_callbacks:
                    await cb(ev)
                    
        except Exception as e:
            self.metrics.errors += 1
            logger.error(f"Tracking processing error: {e}")
            
        ms = (time.time() - t0) * 1000
        self.metrics.record(ms, events_emitted)

    # ── Subscriber management ─────────────────────────────────────────────────

    def add_tracking_callback(self, cb: TrackingCallback) -> None:
        self._track_callbacks.append(cb)

    def add_event_callback(self, cb: EventCallback) -> None:
        self._event_callbacks.append(cb)

    def remove_tracking_callback(self, cb: TrackingCallback) -> None:
        self._track_callbacks = [c for c in self._track_callbacks if c is not cb]

    def remove_event_callback(self, cb: EventCallback) -> None:
        self._event_callbacks = [c for c in self._event_callbacks if c is not cb]

    # ── Core processing ───────────────────────────────────────────────────────

    async def _on_detection_frame(self, det_frame: DetectionFrame) -> None:
        """Called by DetectionPipeline for every inference result."""
        if not self._running:
            return
        try:
            loop = asyncio.get_running_loop()
            tracking_frame, events = await loop.run_in_executor(
                self._executor,
                lambda: self._svc.process(
                    camera_id=det_frame.camera_id,
                    detections=det_frame.detections,
                    timestamp=det_frame.timestamp,
                    frame_idx=det_frame.frame_idx,
                    frame_shape=det_frame.frame_shape,
                ),
            )

            # Cache latest frame per camera for REST
            self._latest_frame[det_frame.camera_id] = tracking_frame
            self.metrics.record(
                ms=tracking_frame.processing_ms,
                events=len(events),
            )

            # Fan-out tracking frames
            await self._dispatch_tracking(tracking_frame)

            # Fan-out visitor events
            for event in events:
                if event.event_type.value == "enter":
                    self.metrics.enter_events += 1
                elif event.event_type.value == "exit":
                    self.metrics.exit_events += 1
                await self._dispatch_event(event)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.metrics.errors += 1
            logger.error(
                "TrackingPipeline error",
                extra={"camera_id": det_frame.camera_id, "error": str(exc)},
            )

    async def _dispatch_tracking(self, frame: TrackingFrame) -> None:
        for cb in list(self._track_callbacks):
            try:
                await cb(frame)
            except Exception as exc:
                logger.error("Tracking callback error", extra={"error": str(exc)})

    async def _dispatch_event(self, event: VisitorEvent) -> None:
        for cb in list(self._event_callbacks):
            try:
                await cb(event)
            except Exception as exc:
                logger.error("Event callback error", extra={"error": str(exc)})

    async def _metrics_log_loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            logger.info(
                "TrackingPipeline metrics",
                extra={
                    "tracking": self.metrics.to_dict(),
                    "service":  self._svc.get_status(),
                },
            )

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "running":   self._running,
            "metrics":   self.metrics.to_dict(),
            "service":   self._svc.get_status(),
            "cameras":   list(self._latest_frame.keys()),
            "subscribers": {
                "tracking": len(self._track_callbacks),
                "events":   len(self._event_callbacks),
            },
        }

    def get_camera_state(self, camera_id: str) -> TrackingFrame | None:
        return self._latest_frame.get(camera_id)

    @property
    def is_running(self) -> bool:
        return self._running


# ── Singleton ─────────────────────────────────────────────────────────────────

_pipeline_instance: TrackingPipeline | None = None


def get_tracking_pipeline() -> TrackingPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = TrackingPipeline()
    return _pipeline_instance


# ── REST endpoints ─────────────────────────────────────────────────────────────

tracking_router = APIRouter(prefix="/tracking", tags=["Tracking"])


@tracking_router.get("/status", summary="Tracking pipeline status and metrics")
async def tracking_status(
    _: None = Depends(require_permission("cameras:read")),
):
    return get_tracking_pipeline().get_status()


@tracking_router.get(
    "/cameras/{camera_id}",
    summary="Latest tracking frame for a camera",
)
async def camera_tracking_state(
    camera_id: str,
    _: None = Depends(require_permission("cameras:read")),
):
    frame = get_tracking_pipeline().get_camera_state(camera_id)
    if frame is None:
        return {"camera_id": camera_id, "visitors": [], "visible_count": 0, "note": "No data yet"}
    return frame.to_api_dict()


@tracking_router.get(
    "/cameras/{camera_id}/visitors",
    summary="Current visible visitors for a camera",
)
async def camera_visitors(
    camera_id: str,
    _: None = Depends(require_permission("cameras:read")),
):
    frame = get_tracking_pipeline().get_camera_state(camera_id)
    if frame is None:
        return {"camera_id": camera_id, "visitors": [], "count": 0}
    return {
        "camera_id":  camera_id,
        "timestamp":  frame.timestamp,
        "visitors":   [v.to_dict() for v in frame.tracked],
        "count":      frame.visible_count,
        "confirmed":  frame.confirmed_count,
        "lost":       frame.lost_count,
    }
