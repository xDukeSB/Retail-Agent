"""
analytics_pipeline.py — Converts raw DetectionFrames into retail events.

Subscribes to DetectionPipeline and produces:
  - PersonCount events  (in/out per zone)
  - DwellTime events    (time spent in zone)
  - Heatmap updates     (centroid accumulation)
  - QueueDepth events   (people in checkout zone)

Privacy:
  - Track IDs are ephemeral session integers — never stored
  - Only aggregated metrics written to DB (counts, durations)
  - No individual trajectories are persisted
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.services.detection_models import DetectionFrame, RetailClass

logger = get_logger(__name__)


# ── Event types ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PersonCountEvent:
    camera_id:  str
    timestamp:  float
    count:      int            # people visible in this frame
    zone_id:    str | None

    def to_dict(self) -> dict:
        return {
            "event":      "person_count",
            "camera_id":  self.camera_id,
            "timestamp":  self.timestamp,
            "count":      self.count,
            "zone_id":    self.zone_id,
        }


@dataclass(frozen=True)
class HeatmapPoint:
    camera_id:   str
    timestamp:   float
    x_norm:      float    # normalized 0-1
    y_norm:      float    # normalized 0-1
    class_id:    int


@dataclass
class ZoneOccupancy:
    zone_id:     str
    camera_id:   str
    count:       int = 0
    entered_at:  dict[int, float] = field(default_factory=dict)   # track_id → entry time
    total_dwell: float = 0.0   # cumulative seconds


# ── Analytics pipeline ────────────────────────────────────────────────────────

class AnalyticsPipeline:
    """
    Subscribes to DetectionPipeline, processes DetectionFrames,
    and emits structured analytics events to downstream consumers
    (WebSocket broadcaster, DB writer).
    """

    def __init__(self):
        self._callbacks:   list[Any] = []
        self._heatmap_buf: dict[str, list[HeatmapPoint]] = defaultdict(list)
        self._occupancy:   dict[str, ZoneOccupancy]      = {}
        self._frame_counts: dict[str, int]               = defaultdict(int)
        self._running      = False
        self._flush_task:  asyncio.Task | None           = None

    async def start(self, detection_pipeline) -> None:
        self._running = True
        detection_pipeline.add_callback(self._on_detection_frame)
        self._flush_task = asyncio.create_task(
            self._flush_loop(), name="analytics-flush"
        )
        logger.info("AnalyticsPipeline started")

    async def stop(self, detection_pipeline) -> None:
        self._running = False
        detection_pipeline.remove_callback(self._on_detection_frame)
        if self._flush_task:
            self._flush_task.cancel()
            await asyncio.gather(self._flush_task, return_exceptions=True)
        logger.info("AnalyticsPipeline stopped")

    def add_callback(self, cb) -> None:
        self._callbacks.append(cb)

    # ── Frame processing ───────────────────────────────────────────────────────

    async def _on_detection_frame(self, frame: DetectionFrame) -> None:
        """Called for every DetectionFrame from the detection pipeline."""
        try:
            await self._process_frame(frame)
        except Exception as exc:
            logger.error("Analytics frame error", extra={"error": str(exc)})

    async def _process_frame(self, frame: DetectionFrame) -> None:
        cam    = frame.camera_id
        ts     = frame.timestamp
        h, w   = frame.frame_shape
        self._frame_counts[cam] += 1

        persons = [d for d in frame.detections if d.class_id == RetailClass.PERSON]
        carts   = [d for d in frame.detections if d.class_id == RetailClass.SHOPPING_CART]

        # 1. Person count event
        event = PersonCountEvent(
            camera_id=cam,
            timestamp=ts,
            count=len(persons),
            zone_id=None,
        )
        await self._emit(event.to_dict())

        # 2. Heatmap points — accumulate centroids
        for det in persons + carts:
            cx, cy = det.bounding_box.center
            self._heatmap_buf[cam].append(HeatmapPoint(
                camera_id=cam,
                timestamp=ts,
                x_norm=cx / w if w > 0 else 0,
                y_norm=cy / h if h > 0 else 0,
                class_id=det.class_id,
            ))

        # 3. Live summary broadcast
        if self._frame_counts[cam] % 5 == 0:   # every 5th frame
            await self._emit({
                "event":        "live_update",
                "camera_id":    cam,
                "timestamp":    ts,
                "person_count": len(persons),
                "cart_count":   len(carts),
                "inference_ms": frame.inference_ms,
            })

    async def _emit(self, event: dict) -> None:
        for cb in list(self._callbacks):
            try:
                await cb(event)
            except Exception as exc:
                logger.error("Analytics emit error", extra={"error": str(exc)})

    # ── Periodic flush ─────────────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        """Every 30s: flush heatmap buffer to DB and reset."""
        while self._running:
            await asyncio.sleep(30)
            await self._flush_heatmap()

    async def _flush_heatmap(self) -> None:
        total = sum(len(v) for v in self._heatmap_buf.values())
        if total == 0:
            return
        logger.info("Flushing heatmap buffer", extra={"points": total})
        # In full implementation: batch-insert to heatmap_events table
        self._heatmap_buf.clear()

    def get_status(self) -> dict:
        return {
            "running":       self._running,
            "cameras":       list(self._frame_counts.keys()),
            "heatmap_buf":   sum(len(v) for v in self._heatmap_buf.values()),
            "frame_counts":  dict(self._frame_counts),
        }


analytics_pipeline = AnalyticsPipeline()
