"""
WebSocket router — real-time live event stream for the dashboard.
Uses a simple in-memory broadcast manager.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("retailai.ws")
router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active_connections.add(ws)
        logger.info(f"WS client connected. Total: {len(self.active_connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self.active_connections.discard(ws)
        logger.info(f"WS client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, data):
        """Broadcasts data to all connected WebSocket clients.
        
        Accepts either a dict (will be JSON-serialized) or a pre-serialized str.
        """
        if not self.active_connections:
            return
        # Serialize only if it's a dict — if already a string, use as-is
        message = json.dumps(data) if isinstance(data, dict) else data
        dead = set()
        for ws in list(self.active_connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        async with self._lock:
            self.active_connections -= dead


manager = ConnectionManager()


async def broadcast_event(data: Dict[str, Any]):
    """Called by other routers to push events to all WS clients."""
    await manager.broadcast(data)


@router.websocket("/live")
async def websocket_live(ws: WebSocket):
    """
    WebSocket endpoint: ws://localhost:8000/ws/live
    Dashboard connects here to receive real-time events.
    """
    await manager.connect(ws)
    try:
        await ws.send_json({"type": "connected", "message": "RetailAI live feed active"})
        while True:
            # Keep connection alive — client sends pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as e:
        logger.error(f"WS error: {e}")
        await manager.disconnect(ws)
