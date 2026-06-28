"""
websocket.py — Real-time WebSocket endpoint for live analytics broadcast.

Clients connect to /api/v1/ws/live and receive:
  - live_update events (person count, cart count per camera)
  - person_count events
  - detection_frame events (optional, gated by query param)

Supports:
  - Multiple concurrent clients
  - Per-client camera filter (?camera_id=...)
  - Heartbeat / ping-pong
  - Graceful disconnect cleanup
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.logging import get_logger
from app.services.analytics_pipeline import analytics_pipeline
from app.services.timeline_service import timeline_service

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket"])


# ── Connection Manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages all active WebSocket connections with fan-out broadcast."""

    def __init__(self):
        self._clients: dict[str, dict] = {}   # client_id → {ws, camera_id, connected_at}

    async def connect(
        self,
        ws: WebSocket,
        client_id: str,
        camera_id: str | None = None,
    ) -> None:
        await ws.accept()
        self._clients[client_id] = {
            "ws":           ws,
            "camera_id":    camera_id,
            "connected_at": time.time(),
        }
        logger.info("WS client connected", extra={"client": client_id, "filter": camera_id})

    def disconnect(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        logger.info("WS client disconnected", extra={"client": client_id})

    async def broadcast(self, event: dict) -> None:
        """Fan-out event to all matching clients."""
        event_camera = event.get("camera_id")
        dead: list[str] = []

        for client_id, meta in list(self._clients.items()):
            # Filter by camera if client requested it
            if meta["camera_id"] and event_camera and meta["camera_id"] != event_camera:
                continue
            try:
                await meta["ws"].send_text(json.dumps(event))
            except Exception:
                dead.append(client_id)

        for cid in dead:
            self.disconnect(cid)

    async def send_to(self, client_id: str, data: dict) -> None:
        meta = self._clients.get(client_id)
        if meta:
            try:
                await meta["ws"].send_text(json.dumps(data))
            except Exception:
                self.disconnect(client_id)

    @property
    def connection_count(self) -> int:
        return len(self._clients)

    def get_status(self) -> dict:
        return {
            "connections": self.connection_count,
            "clients": [
                {
                    "id":          cid,
                    "camera_id":   meta["camera_id"],
                    "connected_s": round(time.time() - meta["connected_at"], 1),
                }
                for cid, meta in self._clients.items()
            ],
        }


ws_manager = ConnectionManager()
timeline_ws_manager = ConnectionManager()


# ── Analytics event hook ───────────────────────────────────────────────────────

async def _broadcast_analytics_event(event: dict) -> None:
    """Registered as analytics_pipeline callback → broadcasts to WS clients."""
    if ws_manager.connection_count > 0:
        await ws_manager.broadcast(event)

async def _broadcast_timeline_event(event: dict) -> None:
    """Registered as timeline_service callback."""
    if timeline_ws_manager.connection_count > 0:
        await timeline_ws_manager.broadcast(event)


# Called once from app lifespan
def register_ws_broadcaster() -> None:
    analytics_pipeline.add_callback(_broadcast_analytics_event)
    timeline_service.add_broadcast_callback(_broadcast_timeline_event)


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/live")
async def ws_live(
    websocket: WebSocket,
    camera_id: str | None = Query(default=None, description="Filter to specific camera"),
):
    """
    WebSocket: real-time analytics stream.

    Connect: ws://host/api/v1/ws/live?camera_id=<optional>

    Messages received (JSON):
      { "event": "live_update", "camera_id": "...", "person_count": N, ... }
      { "event": "person_count", "camera_id": "...", "count": N }
      { "event": "pong", "ts": <unix> }

    Send `{"type":"ping"}` to receive a pong heartbeat.
    """
    import uuid
    client_id = str(uuid.uuid4())[:8]
    await ws_manager.connect(websocket, client_id, camera_id)

    # Immediately send connection ack
    await websocket.send_text(json.dumps({
        "event":     "connected",
        "client_id": client_id,
        "filter":    camera_id,
        "ts":        time.time(),
    }))

    try:
        while True:
            # Wait for client messages (ping, filter change, etc.)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"event": "pong", "ts": time.time()}))
            except asyncio.TimeoutError:
                # Send server-side heartbeat
                await websocket.send_text(json.dumps({"event": "heartbeat", "ts": time.time()}))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(client_id)


@router.websocket("/detection")
async def ws_detection(
    websocket: WebSocket,
    camera_id: str | None = Query(default=None),
):
    """
    WebSocket: raw detection events (bounding boxes per frame).
    Higher bandwidth — use for zone editor / debug overlay only.
    """
    import uuid
    client_id = f"det-{str(uuid.uuid4())[:8]}"
    await ws_manager.connect(websocket, client_id, camera_id)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(client_id)


@router.websocket("/timeline")
async def ws_timeline(
    websocket: WebSocket,
    camera_id: str | None = Query(default=None),
    event_types: str | None = Query(default=None, description="Comma-separated event types")
):
    """
    WebSocket: timeline events stream.
    """
    import uuid
    client_id = f"tl-{str(uuid.uuid4())[:8]}"
    await timeline_ws_manager.connect(websocket, client_id, camera_id)

    allowed_types = [t.strip() for t in event_types.split(",")] if event_types else None
    if allowed_types:
        timeline_ws_manager._clients[client_id]["event_types"] = allowed_types
    
    async def custom_broadcast(event: dict):
        event_camera = event.get("camera_id")
        e_type = event.get("event_type")
        dead = []
        for cid, meta in list(timeline_ws_manager._clients.items()):
            if meta.get("camera_id") and event_camera and meta["camera_id"] != event_camera:
                continue
            if e_type and meta.get("event_types") and e_type not in meta["event_types"]:
                continue
            try:
                await meta["ws"].send_text(json.dumps(event))
            except Exception:
                dead.append(cid)
        for cid in dead:
            timeline_ws_manager.disconnect(cid)
            
    timeline_ws_manager.broadcast = custom_broadcast

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
    finally:
        timeline_ws_manager.disconnect(client_id)
