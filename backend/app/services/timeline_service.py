"""
timeline_service.py — Centralized hub for retail timeline events.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.db.timeline_repository import timeline_repository

logger = get_logger(__name__)


class TimelineService:
    def __init__(self):
        self._broadcast_cbs: list[Callable[[dict], Awaitable[None]]] = []

    def add_broadcast_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        self._broadcast_cbs.append(cb)

    def remove_broadcast_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        self._broadcast_cbs = [c for c in self._broadcast_cbs if c is not cb]

    async def log_event(
        self,
        event_type: str,
        camera_id: str,
        timestamp: float,
        visitor_id: Optional[int] = None,
        details: Optional[dict[str, Any]] = None
    ) -> None:
        """Log a timeline event to DB and broadcast to WS clients."""
        details_json = json.dumps(details) if details else None

        # Fire and forget DB save
        asyncio.create_task(
            self._save_event(event_type, camera_id, timestamp, visitor_id, details_json)
        )

        # Broadcast
        if self._broadcast_cbs:
            event_msg = {
                "stream": "timeline",
                "event_type": event_type,
                "camera_id": camera_id,
                "timestamp": timestamp,
                "visitor_id": visitor_id,
                "details": details or {}
            }
            # Wrap in task so broadcast doesn't block caller
            for cb in self._broadcast_cbs:
                asyncio.create_task(cb(event_msg))

    async def _save_event(
        self,
        event_type: str,
        camera_id: str,
        timestamp: float,
        visitor_id: Optional[int],
        details_json: Optional[str]
    ) -> None:
        try:
            async with AsyncSessionLocal() as session:
                await timeline_repository.create_event(
                    session=session,
                    event_type=event_type,
                    camera_id=camera_id,
                    timestamp=timestamp,
                    visitor_id=visitor_id,
                    details=details_json
                )
                await session.commit()
        except Exception as exc:
            logger.error("Failed to save timeline event", extra={"error": str(exc), "type": event_type})


timeline_service = TimelineService()
