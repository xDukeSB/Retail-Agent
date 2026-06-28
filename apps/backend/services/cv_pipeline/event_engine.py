"""
event_engine.py — Consumes YOLO detections and camera state events.
Updates SQLite database and broadcasts to connected WebSocket clients.
"""
import asyncio
import json
import logging
from sqlalchemy import update
from datetime import datetime

from .engine_manager import engine_manager
from database import AsyncSessionLocal
from models.camera import Camera
from routers.websocket import manager as ws_manager
from .analytics_tracker import AnalyticsTracker
from services.transaction_engine import transaction_engine

logger = logging.getLogger("retailai.cv.events")


class EventEngine:
    def __init__(self):
        self._running = False
        self.analytics = AnalyticsTracker()

    async def run_loop(self):
        self._running = True
        logger.info("[EventEngine] Started processing computer vision events.")

        while self._running:
            try:
                event = await engine_manager.get_next_event()
                await self._process_event(event)
            except asyncio.CancelledError:
                logger.info("[EventEngine] Cancelled.")
                break
            except Exception as e:
                logger.error(f"[EventEngine] Unhandled error processing event: {e}")
                await asyncio.sleep(0.01)

    async def _process_event(self, event: dict):
        event_type = event.get("type")
        camera_id = event.get("camera_id")

        if event_type == "camera_state":
            state = event.get("state", "")

            # Map internal pipeline state → DB status string
            db_status = "inactive"
            if state in ("CONNECTING", "AUTHENTICATING", "STREAM STARTING"):
                db_status = "connecting"
            elif state in ("CONNECTED", "INFERENCE RUNNING"):
                db_status = "active"
            elif "ERROR" in state or "OFFLINE" in state:
                db_status = "error"

            # Persist status to SQLite
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Camera)
                        .where(Camera.id == camera_id)
                        .values(status=db_status, updated_at=datetime.utcnow())
                    )
                    await db.commit()
            except Exception as e:
                logger.error(f"[EventEngine] DB update failed for {camera_id}: {e}")

            # Broadcast to WebSocket clients — pass raw dict, NOT json.dumps()
            await ws_manager.broadcast({
                "type": "camera_status_update",
                "camera_id": camera_id,
                "status": db_status,
                "pipeline_state": state,
                "details": event.get("details", "")
            })

        elif event_type == "detections":
            detections = event.get("detections", [])
            timestamp = event.get("timestamp")

            # Update stateful tracking (zones, dwell, heatmap, etc.)
            await self.analytics.process_frame_detections(camera_id, timestamp, detections)

            # ── Transaction Intelligence Engine ──────────────────────────
            # Gather zone crossings that were computed during this frame
            # The analytics tracker writes them to DB; we pass them to the
            # transaction engine for in-memory signal detection.
            zone_crossings = self.analytics.get_last_frame_crossings(camera_id)
            txn_events = await transaction_engine.process_frame(
                camera_id=camera_id,
                timestamp=timestamp,
                detections=detections,
                zone_crossings=zone_crossings,
            )

            # Broadcast transaction state updates
            if ws_manager.active_connections:
                for txn_event in txn_events:
                    await ws_manager.broadcast(txn_event)

            # Only broadcast if clients are connected (saves CPU)
            if ws_manager.active_connections:
                await ws_manager.broadcast({
                    "type": "live_detections",
                    "camera_id": camera_id,
                    "timestamp": timestamp,
                    "inference_time_ms": event.get("inference_time_ms"),
                    "frame_count": event.get("frame_count", 0),
                    "detections": detections,
                })

    async def stop(self):
        self._running = False
        logger.info("[EventEngine] Stopped.")
