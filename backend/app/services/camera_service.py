"""
camera_service.py — Single-camera RTSP ingestion engine.

Each CameraService manages one RTSP stream:
  - AsyncIO-native with blocking OpenCV calls offloaded to a thread pool
  - Frame buffering via asyncio.Queue
  - Exponential-backoff auto-reconnect
  - FFmpeg transport fallback (TCP → UDP)
  - Frame subscriber pattern for downstream consumers (CV pipeline)

Supported stream types:
  - RTSP (IP cameras, NVRs, DVRs)
  - RTMP
  - HTTP MJPEG
  - Local files / test streams (rtsp://user:pass@host/stream)
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Awaitable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import cv2
import numpy as np

from app.core.logging import get_logger
from app.services.stream_health import StreamHealthMonitor, StreamState

logger = get_logger(__name__)

# Type alias for frame callbacks
FrameCallback = Callable[[str, np.ndarray, float], Awaitable[None]]


class ReconnectPolicy:
    """Exponential backoff reconnect schedule."""
    def __init__(
        self,
        initial_delay: float = 2.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        max_attempts: int = 0,    # 0 = infinite
    ):
        self.initial_delay = initial_delay
        self.max_delay     = max_delay
        self.multiplier    = multiplier
        self.max_attempts  = max_attempts
        self._attempt      = 0
        self._current_delay = initial_delay

    def next_delay(self) -> float:
        self._attempt      += 1
        delay               = min(self._current_delay, self.max_delay)
        self._current_delay = min(self._current_delay * self.multiplier, self.max_delay)
        return delay

    def reset(self) -> None:
        self._attempt       = 0
        self._current_delay = self.initial_delay

    @property
    def attempts(self) -> int:
        return self._attempt

    def should_retry(self) -> bool:
        if self.max_attempts == 0:
            return True
        return self._attempt < self.max_attempts


class CameraService:
    """
    Manages a single RTSP camera stream.

    Usage:
        svc = CameraService(camera_id="cam-1", rtsp_url="rtsp://...", target_fps=10)
        svc.add_frame_callback(my_async_callback)
        await svc.start()
        # later:
        await svc.stop()
    """

    # OpenCV capture properties
    _CV_BACKEND_FLAGS = cv2.CAP_FFMPEG

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        target_fps: int = 10,
        buffer_size: int = 30,
        reconnect_policy: ReconnectPolicy | None = None,
        resolution: tuple[int, int] | None = None,
        ffmpeg_transport: str = "tcp",   # tcp | udp
        extra_options: dict[str, Any] | None = None,
    ):
        self.camera_id        = camera_id
        self.rtsp_url         = rtsp_url
        self.target_fps       = target_fps
        self.buffer_size      = buffer_size
        self.reconnect_policy = reconnect_policy or ReconnectPolicy()
        self.resolution       = resolution
        self.ffmpeg_transport = ffmpeg_transport
        self.extra_options    = extra_options or {}

        self.health   = StreamHealthMonitor(camera_id=camera_id, target_fps=target_fps)
        self._queue:  asyncio.Queue[tuple[np.ndarray, float]] = asyncio.Queue(maxsize=buffer_size)
        self._callbacks: list[FrameCallback] = []
        self._stop_event  = asyncio.Event()
        self._running     = False
        self._capture:    cv2.VideoCapture | None = None
        self._executor    = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"cam-{camera_id[:8]}")
        self._tasks:      list[asyncio.Task] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_frame_callback(self, callback: FrameCallback) -> None:
        """Register an async callback to receive decoded frames."""
        self._callbacks.append(callback)

    def remove_frame_callback(self, callback: FrameCallback) -> None:
        self._callbacks = [c for c in self._callbacks if c is not callback]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        await self.health.transition(StreamState.CONNECTING)
        self._tasks = [
            asyncio.create_task(self._ingest_loop(),    name=f"ingest-{self.camera_id[:8]}"),
            asyncio.create_task(self._dispatch_loop(),  name=f"dispatch-{self.camera_id[:8]}"),
            asyncio.create_task(self._health_loop(),    name=f"health-{self.camera_id[:8]}"),
        ]
        logger.info("Camera service started", extra={"camera_id": self.camera_id, "url": self._safe_url()})

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._close_capture()
        await self.health.transition(StreamState.DISCONNECTED)
        logger.info("Camera service stopped", extra={"camera_id": self.camera_id})

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Capture management ─────────────────────────────────────────────────────

    def _build_capture(self) -> cv2.VideoCapture:
        """Build an OpenCV VideoCapture with FFmpeg options."""
        cap = cv2.VideoCapture(self.rtsp_url, self._CV_BACKEND_FLAGS)

        # FFmpeg transport (TCP is more reliable, UDP lower latency)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"H264"))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # Minimize buffering lag

        # RTSP transport via OpenCV environment variable
        import os
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{self.ffmpeg_transport}|"
            "stimeout;5000000|"          # 5s socket timeout
            "analyzeduration;500000|"    # 0.5s analyze (faster open)
            "fflags;nobuffer|"
            "flags;low_delay"
        )

        if self.resolution:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])

        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        return cap

    async def _open_capture(self) -> bool:
        """Open the capture in a thread (OpenCV is blocking)."""
        loop = asyncio.get_running_loop()
        try:
            cap = await loop.run_in_executor(self._executor, self._build_capture)
            opened = await loop.run_in_executor(self._executor, lambda: cap.isOpened())
            if opened:
                self._capture = cap
                return True
            cap.release()
            return False
        except Exception as exc:
            logger.error(
                "Failed to open capture",
                extra={"camera_id": self.camera_id, "error": str(exc)},
            )
            return False

    async def _close_capture(self) -> None:
        if self._capture:
            loop = asyncio.get_running_loop()
            cap, self._capture = self._capture, None
            await loop.run_in_executor(self._executor, cap.release)

    # ── Ingest loop ────────────────────────────────────────────────────────────

    async def _ingest_loop(self) -> None:
        """
        Main ingest loop — opens stream, reads frames, handles reconnects.
        Runs until stop() is called.
        """
        self.reconnect_policy.reset()

        while not self._stop_event.is_set():
            success = await self._open_capture()
            if not success:
                await self.health.transition(
                    StreamState.RECONNECTING,
                    error="Failed to open RTSP stream",
                )
                await self._wait_for_reconnect()
                continue

            await self.health.transition(StreamState.ACTIVE)
            self.reconnect_policy.reset()
            self.health.reset_metrics()
            logger.info("RTSP stream opened", extra={"camera_id": self.camera_id})

            # Frame read loop
            consecutive_failures = 0
            frame_interval = 1.0 / self.target_fps

            while not self._stop_event.is_set():
                t0 = time.perf_counter()

                frame = await self._read_frame()
                if frame is None:
                    consecutive_failures += 1
                    self.health.record_dropped_frame()
                    if consecutive_failures >= 10:
                        logger.warning(
                            "Too many consecutive frame failures",
                            extra={"camera_id": self.camera_id, "failures": consecutive_failures},
                        )
                        break
                    await asyncio.sleep(0.05)
                    continue

                consecutive_failures = 0
                latency_ms = (time.perf_counter() - t0) * 1000
                h, w = frame.shape[:2]
                self.health.record_frame(latency_ms=latency_ms, resolution=(w, h))

                # Push to buffer (drop oldest if full — prefer fresh frames)
                timestamp = time.time()
                if self._queue.full():
                    try:
                        self._queue.get_nowait()
                        self.health.record_dropped_frame()
                    except asyncio.QueueEmpty:
                        pass
                await self._queue.put((frame, timestamp))

                # Throttle to target FPS
                elapsed = time.perf_counter() - t0
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            # Stream lost — prepare reconnect
            await self._close_capture()
            if self._running:
                await self.health.transition(
                    StreamState.RECONNECTING,
                    error="Stream read loop ended unexpectedly",
                )
                await self._wait_for_reconnect()

    async def _read_frame(self) -> np.ndarray | None:
        """Read a single frame in a thread executor."""
        if not self._capture:
            return None
        loop = asyncio.get_running_loop()
        try:
            ret, frame = await loop.run_in_executor(
                self._executor, self._capture.read
            )
            return frame if ret and frame is not None and frame.size > 0 else None
        except Exception:
            return None

    async def _wait_for_reconnect(self) -> None:
        """Sleep for the reconnect backoff delay unless stopped."""
        if not self.reconnect_policy.should_retry():
            await self.health.transition(StreamState.ERROR, error="Max reconnect attempts reached")
            self._running = False
            return
        delay = self.reconnect_policy.next_delay()
        logger.info(
            "Reconnecting camera stream",
            extra={
                "camera_id": self.camera_id,
                "attempt":   self.reconnect_policy.attempts,
                "delay_s":   delay,
            },
        )
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass  # Normal — proceed to reconnect

    # ── Dispatch loop ──────────────────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        """
        Consumes frames from the buffer and calls all registered callbacks.
        Runs in a separate task so slow callbacks don't block ingestion.
        """
        while not self._stop_event.is_set():
            try:
                frame, timestamp = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            for callback in list(self._callbacks):
                try:
                    await callback(self.camera_id, frame, timestamp)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "Frame callback error",
                        extra={"camera_id": self.camera_id, "error": str(exc)},
                    )

    # ── Health loop ────────────────────────────────────────────────────────────

    async def _health_loop(self) -> None:
        """Periodically checks for FPS degradation."""
        while not self._stop_event.is_set():
            await asyncio.sleep(5.0)
            await self.health.check_degradation()

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _safe_url(self) -> str:
        """Redact credentials from URL for logging."""
        import re
        return re.sub(r"://([^:@]+:[^@]+@)", "://<redacted>@", self.rtsp_url)

    def get_health(self) -> dict:
        return self.health.snapshot().to_dict()
