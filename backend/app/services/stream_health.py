"""
stream_health.py — Real-time stream health monitoring.

Tracks per-camera health metrics using a sliding window for FPS,
a state machine for connection status, and diagnostic snapshots.

States:
    INITIALIZING → CONNECTING → ACTIVE → DEGRADED → ERROR
                                    ↑___________________________↓ (reconnect)
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Deque

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── State Machine ─────────────────────────────────────────────────────────────

class StreamState(str, Enum):
    INITIALIZING  = "initializing"
    CONNECTING    = "connecting"
    ACTIVE        = "active"
    DEGRADED      = "degraded"     # Connected but below target FPS
    ERROR         = "error"        # Fatal error
    DISCONNECTED  = "disconnected" # Intentionally stopped
    RECONNECTING  = "reconnecting" # Auto-reconnect in progress


VALID_TRANSITIONS: dict[StreamState, set[StreamState]] = {
    StreamState.INITIALIZING:  {StreamState.CONNECTING, StreamState.ERROR},
    StreamState.CONNECTING:    {StreamState.ACTIVE, StreamState.ERROR, StreamState.RECONNECTING},
    StreamState.ACTIVE:        {StreamState.DEGRADED, StreamState.ERROR, StreamState.DISCONNECTED, StreamState.RECONNECTING},
    StreamState.DEGRADED:      {StreamState.ACTIVE, StreamState.ERROR, StreamState.RECONNECTING, StreamState.DISCONNECTED},
    StreamState.ERROR:         {StreamState.RECONNECTING, StreamState.DISCONNECTED},
    StreamState.RECONNECTING:  {StreamState.CONNECTING, StreamState.ERROR, StreamState.DISCONNECTED},
    StreamState.DISCONNECTED:  {StreamState.CONNECTING},
}


# ── Health Snapshot ────────────────────────────────────────────────────────────

@dataclass
class HealthSnapshot:
    camera_id:       str
    state:           StreamState
    avg_fps:         float
    target_fps:      int
    fps_ratio:       float           # avg_fps / target_fps
    frame_count:     int
    dropped_frames:  int
    drop_rate:       float           # dropped / total
    reconnect_count: int
    last_frame_at:   datetime | None
    last_error:      str | None
    uptime_seconds:  float
    latency_ms:      float | None    # Last frame decode latency
    resolution:      tuple[int, int] | None
    is_healthy:      bool

    def to_dict(self) -> dict:
        return {
            "camera_id":       self.camera_id,
            "state":           self.state.value,
            "avg_fps":         round(self.avg_fps, 2),
            "target_fps":      self.target_fps,
            "fps_ratio":       round(self.fps_ratio, 3),
            "frame_count":     self.frame_count,
            "dropped_frames":  self.dropped_frames,
            "drop_rate":       round(self.drop_rate, 4),
            "reconnect_count": self.reconnect_count,
            "last_frame_at":   self.last_frame_at.isoformat() if self.last_frame_at else None,
            "last_error":      self.last_error,
            "uptime_seconds":  round(self.uptime_seconds, 1),
            "latency_ms":      round(self.latency_ms, 2) if self.latency_ms else None,
            "resolution":      list(self.resolution) if self.resolution else None,
            "is_healthy":      self.is_healthy,
        }


# ── Health Monitor ─────────────────────────────────────────────────────────────

class StreamHealthMonitor:
    """
    Per-camera health tracker. Thread-safe for use with asyncio + threads.

    FPS is calculated using a sliding window of the last N frame timestamps.
    Degraded = avg_fps < target_fps * 0.6 for > 10 seconds.
    """

    FPS_WINDOW_SIZE = 60           # frames
    DEGRADED_THRESHOLD = 0.60      # fraction of target FPS
    DEGRADED_GRACE_SECONDS = 10.0  # must be degraded for this long to trigger state change

    def __init__(self, camera_id: str, target_fps: int = 10):
        self.camera_id       = camera_id
        self.target_fps      = target_fps
        self._state          = StreamState.INITIALIZING
        self._frame_times:   Deque[float]   = deque(maxlen=self.FPS_WINDOW_SIZE)
        self._latencies:     Deque[float]   = deque(maxlen=30)
        self._frame_count    = 0
        self._dropped_frames = 0
        self._reconnect_count = 0
        self._last_error:    str | None     = None
        self._last_frame_at: datetime | None = None
        self._resolution:    tuple[int, int] | None = None
        self._start_time     = time.monotonic()
        self._degraded_since: float | None  = None
        self._lock           = asyncio.Lock()

    # ── State machine ──────────────────────────────────────────────────────────

    @property
    def state(self) -> StreamState:
        return self._state

    async def transition(self, new_state: StreamState, error: str | None = None) -> None:
        async with self._lock:
            if new_state not in VALID_TRANSITIONS.get(self._state, set()):
                logger.debug(
                    "Invalid state transition ignored",
                    extra={
                        "camera_id": self.camera_id,
                        "from": self._state.value,
                        "to": new_state.value,
                    },
                )
                return

            old = self._state.value
            self._state = new_state
            if error:
                self._last_error = error
            if new_state == StreamState.RECONNECTING:
                self._reconnect_count += 1

            logger.info(
                "Camera state changed",
                extra={
                    "camera_id":  self.camera_id,
                    "from_state": old,
                    "to_state":   new_state.value,
                    "error":      error,
                },
            )

    # ── Frame accounting ───────────────────────────────────────────────────────

    def record_frame(self, latency_ms: float | None = None, resolution: tuple[int, int] | None = None) -> None:
        """Call for every successfully decoded frame."""
        now = time.monotonic()
        self._frame_times.append(now)
        self._frame_count += 1
        self._last_frame_at = datetime.now(timezone.utc)
        if latency_ms is not None:
            self._latencies.append(latency_ms)
        if resolution:
            self._resolution = resolution
        # Clear degraded tracking if we're receiving frames well
        if self.avg_fps >= self.target_fps * self.DEGRADED_THRESHOLD:
            self._degraded_since = None

    def record_dropped_frame(self) -> None:
        """Call when a frame read attempt returns None/empty."""
        self._dropped_frames += 1

    # ── Metrics ────────────────────────────────────────────────────────────────

    @property
    def avg_fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        window = list(self._frame_times)
        elapsed = window[-1] - window[0]
        if elapsed <= 0:
            return 0.0
        return (len(window) - 1) / elapsed

    @property
    def avg_latency_ms(self) -> float | None:
        if not self._latencies:
            return None
        return sum(self._latencies) / len(self._latencies)

    @property
    def drop_rate(self) -> float:
        total = self._frame_count + self._dropped_frames
        if total == 0:
            return 0.0
        return self._dropped_frames / total

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def is_healthy(self) -> bool:
        return (
            self._state in (StreamState.ACTIVE, StreamState.DEGRADED)
            and self._last_frame_at is not None
            and self.avg_fps > 0
        )

    async def check_degradation(self) -> None:
        """
        Call periodically (e.g. every 5s) to detect FPS degradation
        and trigger DEGRADED state automatically.
        """
        if self._state != StreamState.ACTIVE:
            return
        fps = self.avg_fps
        if fps < self.target_fps * self.DEGRADED_THRESHOLD:
            now = time.monotonic()
            if self._degraded_since is None:
                self._degraded_since = now
            elif now - self._degraded_since >= self.DEGRADED_GRACE_SECONDS:
                await self.transition(
                    StreamState.DEGRADED,
                    error=f"FPS degraded: {fps:.1f} < {self.target_fps * self.DEGRADED_THRESHOLD:.1f}",
                )
        elif self._state == StreamState.DEGRADED and fps >= self.target_fps * self.DEGRADED_THRESHOLD:
            await self.transition(StreamState.ACTIVE)
            self._degraded_since = None

    def snapshot(self) -> HealthSnapshot:
        fps = self.avg_fps
        return HealthSnapshot(
            camera_id=self.camera_id,
            state=self._state,
            avg_fps=fps,
            target_fps=self.target_fps,
            fps_ratio=fps / self.target_fps if self.target_fps > 0 else 0,
            frame_count=self._frame_count,
            dropped_frames=self._dropped_frames,
            drop_rate=self.drop_rate,
            reconnect_count=self._reconnect_count,
            last_frame_at=self._last_frame_at,
            last_error=self._last_error,
            uptime_seconds=self.uptime_seconds,
            latency_ms=self.avg_latency_ms,
            resolution=self._resolution,
            is_healthy=self.is_healthy,
        )

    def reset_metrics(self) -> None:
        """Reset frame counters on reconnect."""
        self._frame_times.clear()
        self._latencies.clear()
        self._degraded_since = None
