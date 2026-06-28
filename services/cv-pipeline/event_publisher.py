"""
Event publisher — sends CV pipeline events to the backend API.
Uses async httpx with retry logic. Batches events for efficiency.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("cv-pipeline.publisher")


class EventPublisher:
    """
    Async HTTP client that publishes CV events to the FastAPI backend.
    Retries on failure — resilient to momentary backend restarts.
    """

    def __init__(self, backend_url: str, camera_id: str):
        self.backend_url = backend_url.rstrip("/")
        self.camera_id = camera_id
        self._client: Optional[httpx.AsyncClient] = None
        self._failed_queue: List[Dict] = []

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.backend_url,
            timeout=httpx.Timeout(5.0),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _post(self, endpoint: str, data: Dict, retries: int = 3) -> bool:
        for attempt in range(retries):
            try:
                resp = await self._client.post(f"/api/events{endpoint}", json=data)
                resp.raise_for_status()
                return True
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning(f"Event publish failed ({endpoint}): {e}")
        return False

    def _ts(self, ts: Optional[float] = None) -> str:
        t = ts or datetime.now(timezone.utc).timestamp()
        return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()

    async def track_start(self, track_id: int, x: float, y: float, ts: float):
        await self._post("/track/start", {
            "camera_id": self.camera_id,
            "session_track_id": track_id,
            "timestamp": self._ts(ts),
            "x": x,
            "y": y,
        })

    async def track_end(
        self,
        track_id: int,
        entry_time: float,
        exit_time: float,
        dwell_seconds: float,
        zones_visited: List[str],
        path: List[List[float]],
    ):
        await self._post("/track/end", {
            "camera_id": self.camera_id,
            "session_track_id": track_id,
            "entry_time": self._ts(entry_time),
            "exit_time": self._ts(exit_time),
            "dwell_seconds": dwell_seconds,
            "zones_visited": zones_visited,
            "path_json": path,
        })

    async def zone_crossing(
        self,
        track_id: int,
        zone_name: str,
        zone_type: str,
        event_type: str,
        x: float,
        y: float,
        ts: float,
    ):
        await self._post("/zone-crossing", {
            "camera_id": self.camera_id,
            "session_track_id": track_id,
            "zone_name": zone_name,
            "zone_type": zone_type,
            "event_type": event_type,
            "timestamp": self._ts(ts),
            "x": x,
            "y": y,
        })

    async def queue_snapshot(
        self,
        zone_name: str,
        queue_depth: int,
        avg_wait: Optional[float],
        max_wait: Optional[float],
        ts: float,
    ):
        await self._post("/queue", {
            "camera_id": self.camera_id,
            "zone_name": zone_name,
            "queue_depth": queue_depth,
            "avg_wait_seconds": avg_wait,
            "max_wait_seconds": max_wait,
            "timestamp": self._ts(ts),
        })

    async def push_heatmap(self, date_str: str, cells: List[Dict]):
        if not cells:
            return
        await self._post("/heatmap/batch", {
            "camera_id": self.camera_id,
            "date": date_str,
            "cells": cells,
        })

    async def update_camera_status(self, status: str):
        try:
            await self._client.post(
                f"/api/cameras/{self.camera_id}/status",
                params={"status_val": status},
            )
        except Exception:
            pass
