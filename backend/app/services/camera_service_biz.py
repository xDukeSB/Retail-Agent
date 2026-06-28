"""
camera_service_biz.py — Business logic service layer for camera management.

Sits between the API layer and the repository layer:
  - RTSP URL validation (format + reachability)
  - Connection testing (OpenCV probe with timeout)
  - Health score computation (composite metric 0-100)
  - Periodic health sync (writes CameraManager metrics → DB)
  - Business rules enforcement
"""
from __future__ import annotations

import asyncio
import re
import socket
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.camera_repository import camera_repo
from app.services.camera_manager import camera_manager
from app.services.stream_health import StreamState

logger = get_logger(__name__)

_probe_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rtsp-probe")

# ── RTSP URL Patterns ─────────────────────────────────────────────────────────

_RTSP_PATTERN = re.compile(
    r"^(rtsp|rtsps|rtmp|http|https)://"  # scheme
    r"([^/:@]+(?::[^@]+)?@)?"            # optional user:pass@
    r"([A-Za-z0-9\-_.]+)"               # host
    r"(:\d{1,5})?"                       # optional port
    r"(/.*)?$"                           # optional path
)


class RTSPValidationResult:
    def __init__(self, valid: bool, error: str | None = None, details: dict | None = None):
        self.valid   = valid
        self.error   = error
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"valid": self.valid, "error": self.error, "details": self.details}


class ConnectionTestResult:
    def __init__(
        self,
        reachable: bool,
        latency_ms: float | None = None,
        resolution: tuple[int, int] | None = None,
        fps: float | None = None,
        error: str | None = None,
    ):
        self.reachable   = reachable
        self.latency_ms  = latency_ms
        self.resolution  = resolution
        self.fps         = fps
        self.error       = error

    def to_dict(self) -> dict:
        return {
            "reachable":  self.reachable,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms else None,
            "resolution": list(self.resolution) if self.resolution else None,
            "fps":        round(self.fps, 1) if self.fps else None,
            "error":      self.error,
        }


class CameraBusinessService:
    """
    Encapsulates all business logic for camera management.
    Never touches HTTP — only DB, OS, and network.
    """

    # ── URL Validation ─────────────────────────────────────────────────────────

    def validate_rtsp_url(self, url: str) -> RTSPValidationResult:
        """
        Validates RTSP URL format. Does NOT test network connectivity.
        Use test_connection() for that.
        """
        if not url or not isinstance(url, str):
            return RTSPValidationResult(False, "URL must be a non-empty string")

        url = url.strip()
        if len(url) > 1024:
            return RTSPValidationResult(False, "URL exceeds maximum length of 1024 characters")

        match = _RTSP_PATTERN.match(url)
        if not match:
            return RTSPValidationResult(
                False,
                "Invalid URL format. Expected: rtsp://[user:pass@]host[:port][/path]",
            )

        scheme = match.group(1)
        host   = match.group(3)
        port_s = match.group(4)

        details: dict[str, Any] = {
            "scheme": scheme,
            "host":   host,
            "port":   int(port_s[1:]) if port_s else self._default_port(scheme),
            "has_credentials": "@" in url,
        }

        if port_s:
            port = int(port_s[1:])
            if not (1 <= port <= 65535):
                return RTSPValidationResult(False, f"Invalid port: {port}. Must be 1-65535")

        return RTSPValidationResult(True, details=details)

    def _default_port(self, scheme: str) -> int:
        return {"rtsp": 554, "rtsps": 322, "rtmp": 1935, "http": 80, "https": 443}.get(scheme, 554)

    # ── Connection Test ────────────────────────────────────────────────────────

    async def test_connection(
        self,
        rtsp_url: str,
        timeout_seconds: int = 8,
        username: str | None = None,
        password: str | None = None,
    ) -> ConnectionTestResult:
        """
        Probe an RTSP stream:
        1. TCP socket reachability check (fast)
        2. OpenCV VideoCapture frame grab (full probe)
        Returns latency, resolution, FPS if successful.
        """
        # Validate format first
        validation = self.validate_rtsp_url(rtsp_url)
        if not validation.valid:
            return ConnectionTestResult(False, error=validation.error)

        # Inject credentials if provided
        full_url = self._inject_credentials(rtsp_url, username, password)

        # Step 1: TCP reachability
        host    = validation.details["host"]
        port    = validation.details["port"]
        tcp_ok, tcp_ms = await self._tcp_ping(host, port, timeout=5)
        if not tcp_ok:
            return ConnectionTestResult(
                False,
                error=f"Host {host}:{port} is not reachable (TCP timeout)",
            )

        # Step 2: OpenCV probe
        loop   = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _probe_executor,
            lambda: self._opencv_probe(full_url, timeout_seconds),
        )
        result.latency_ms = tcp_ms
        return result

    async def _tcp_ping(self, host: str, port: int, timeout: float) -> tuple[bool, float | None]:
        """Check if host:port is TCP-reachable."""
        t0 = time.perf_counter()
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: socket.create_connection((host, port), timeout=timeout)),
                timeout=timeout,
            )
            ms = (time.perf_counter() - t0) * 1000
            return True, ms
        except Exception:
            return False, None

    def _opencv_probe(self, url: str, timeout: int) -> ConnectionTestResult:
        """Blocking OpenCV probe — run in thread executor."""
        try:
            import cv2
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;tcp|stimeout;{timeout * 1_000_000}|"
                "analyzeduration;500000|fflags;nobuffer"
            )
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                return ConnectionTestResult(False, error="Stream could not be opened")

            t0  = time.perf_counter()
            ret, frame = cap.read()
            ms  = (time.perf_counter() - t0) * 1000

            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            if not ret or frame is None:
                return ConnectionTestResult(False, error="Stream opened but no frame received")

            return ConnectionTestResult(
                reachable=True,
                latency_ms=ms,
                resolution=(w, h) if w and h else None,
                fps=fps if fps > 0 else None,
            )
        except ImportError:
            return ConnectionTestResult(False, error="OpenCV not installed on this server")
        except Exception as exc:
            return ConnectionTestResult(False, error=str(exc))

    @staticmethod
    def _inject_credentials(url: str, username: str | None, password: str | None) -> str:
        if username and password and "@" not in url:
            proto, rest = url.split("://", 1)
            return f"{proto}://{urllib.parse.quote(username)}:{urllib.parse.quote(password)}@{rest}"
        return url

    # ── Health Score ───────────────────────────────────────────────────────────

    def compute_health_score(self, health: dict) -> float:
        """
        Composite health score 0–100 from live stream metrics.

        Weights:
          - FPS ratio (50%):       avg_fps / target_fps
          - Drop rate (25%):       1 - drop_rate
          - Reconnect penalty (15%): decays with reconnect count
          - Recency (10%):         penalised if no frame for > 30s
        """
        if health.get("state") in ("disconnected", "inactive", "error"):
            return 0.0
        if not health.get("is_healthy", False):
            return max(0.0, 10.0)

        fps_score       = min(health.get("fps_ratio", 0) * 100, 100) * 0.50
        drop_score      = (1 - min(health.get("drop_rate", 0), 1)) * 100 * 0.25
        reconnect_count = health.get("reconnect_count", 0)
        reconnect_score = max(0, 100 - reconnect_count * 5) * 0.15

        last_frame_at = health.get("last_frame_at")
        if last_frame_at:
            from datetime import datetime, timezone
            last = datetime.fromisoformat(last_frame_at)
            age  = (datetime.now(timezone.utc) - last).total_seconds()
            recency_score = max(0, 100 - age * 3.3) * 0.10
        else:
            recency_score = 0.0

        score = fps_score + drop_score + reconnect_score + recency_score
        return round(min(max(score, 0.0), 100.0), 1)

    # ── Periodic Health Sync ───────────────────────────────────────────────────

    async def sync_health_to_db(self, db: AsyncSession) -> int:
        """
        Flush live CameraManager metrics into the database.
        Call this from a background task (e.g. every 30s).
        Returns the number of cameras updated.
        """
        updated = 0
        all_health = camera_manager.get_all_health()
        for camera_id, health in all_health.items():
            score = self.compute_health_score(health)
            await camera_repo.update_health(
                db,
                camera_id,
                status=health.get("state", "unknown"),
                avg_fps=health.get("avg_fps"),
                health_score=score,
                last_error=health.get("last_error"),
            )
            updated += 1
        return updated

    # ── Business Rules ─────────────────────────────────────────────────────────

    async def ensure_no_duplicate_url(
        self,
        db: AsyncSession,
        rtsp_url: str,
        exclude_id: str | None = None,
    ) -> bool:
        """Returns True if URL is unique (or belongs to exclude_id)."""
        existing = await camera_repo.find_by_rtsp_url(db, rtsp_url)
        if existing is None:
            return True
        if exclude_id and existing.id == exclude_id:
            return True
        return False

    def get_health_label(self, score: float | None) -> str:
        if score is None:
            return "Unknown"
        if score >= 90:
            return "Excellent"
        if score >= 70:
            return "Good"
        if score >= 50:
            return "Fair"
        if score >= 25:
            return "Poor"
        return "Critical"


# Singleton
camera_biz = CameraBusinessService()
