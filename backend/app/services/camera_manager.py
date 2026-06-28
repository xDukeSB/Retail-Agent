"""
camera_manager.py — Multi-camera orchestrator.

Manages the lifecycle of all CameraService instances:
  - Dynamic camera registration (add/remove at runtime)
  - Global frame subscriber routing
  - Health aggregation across all cameras
  - Startup: auto-loads all enabled cameras from the registry
  - Graceful shutdown

Designed as a singleton service that lives in the FastAPI lifespan context.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.services.camera_registry import Camera, CameraRegistry
from app.services.camera_service import CameraService, FrameCallback, ReconnectPolicy
from app.services.stream_health import StreamState

logger = get_logger(__name__)


class CameraManager:
    """
    Singleton orchestrator for all camera streams.

    Attach to FastAPI lifespan:

        @asynccontextmanager
        async def lifespan(app):
            await camera_manager.start(db_session_factory)
            yield
            await camera_manager.stop()
    """

    def __init__(self):
        self._services:     dict[str, CameraService] = {}   # camera_id → service
        self._callbacks:    list[FrameCallback]       = []   # global subscribers
        self._registry      = CameraRegistry()
        self._running       = False
        self._lock          = asyncio.Lock()
        self._db_factory    = None  # set on start()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, db_session_factory) -> None:
        """
        Start the manager. Loads all enabled cameras from DB and
        begins ingesting. Call from FastAPI lifespan.
        """
        if self._running:
            return
        self._running    = True
        self._db_factory = db_session_factory

        async with db_session_factory() as db:
            cameras = await self._registry.list_cameras(db, include_inactive=False)

        logger.info("CameraManager starting", extra={"camera_count": len(cameras)})

        for cam in cameras:
            if cam.is_enabled:
                await self._start_service(cam)

        logger.info("CameraManager ready", extra={"active": len(self._services)})

    async def stop(self) -> None:
        """Stop all camera streams. Call from FastAPI lifespan shutdown."""
        if not self._running:
            return
        self._running = False
        logger.info("CameraManager shutting down", extra={"cameras": len(self._services)})
        async with self._lock:
            tasks = [svc.stop() for svc in self._services.values()]
            await asyncio.gather(*tasks, return_exceptions=True)
            self._services.clear()
        logger.info("CameraManager stopped")

    # ── Dynamic registration ───────────────────────────────────────────────────

    async def add_camera(self, camera: Camera) -> CameraService:
        """Register and immediately start a camera stream."""
        async with self._lock:
            if camera.id in self._services:
                logger.warning("Camera already running", extra={"camera_id": camera.id})
                return self._services[camera.id]
            svc = await self._start_service(camera)
        logger.info("Camera dynamically added", extra={"camera_id": camera.id})
        return svc

    async def remove_camera(self, camera_id: str) -> bool:
        """Stop and unregister a camera stream."""
        async with self._lock:
            svc = self._services.pop(camera_id, None)
            if svc is None:
                return False
            await svc.stop()
        logger.info("Camera removed", extra={"camera_id": camera_id})
        return True

    async def restart_camera(self, camera_id: str) -> bool:
        """Force-restart a single camera service."""
        async with self._lock:
            svc = self._services.get(camera_id)
            if not svc:
                return False
            await svc.stop()
        async with self._db_factory() as db:
            cam = await self._registry.get_camera(db, camera_id)
        if not cam:
            return False
        await self.add_camera(cam)
        logger.info("Camera restarted", extra={"camera_id": camera_id})
        return True

    # ── Frame subscribers ──────────────────────────────────────────────────────

    def add_global_callback(self, callback: FrameCallback) -> None:
        """Subscribe to frames from ALL cameras."""
        self._callbacks.append(callback)
        for svc in self._services.values():
            svc.add_frame_callback(callback)

    def remove_global_callback(self, callback: FrameCallback) -> None:
        self._callbacks = [c for c in self._callbacks if c is not callback]
        for svc in self._services.values():
            svc.remove_frame_callback(callback)

    # ── Health & status ────────────────────────────────────────────────────────

    def get_health(self, camera_id: str) -> dict | None:
        svc = self._services.get(camera_id)
        return svc.get_health() if svc else None

    def get_all_health(self) -> dict[str, dict]:
        return {cid: svc.get_health() for cid, svc in self._services.items()}

    def get_active_camera_ids(self) -> list[str]:
        return [
            cid for cid, svc in self._services.items()
            if svc.health.state == StreamState.ACTIVE
        ]

    def get_summary(self) -> dict[str, Any]:
        total   = len(self._services)
        active  = sum(1 for s in self._services.values() if s.health.state == StreamState.ACTIVE)
        error   = sum(1 for s in self._services.values() if s.health.state == StreamState.ERROR)
        return {
            "total":         total,
            "active":        active,
            "error":         error,
            "degraded":      total - active - error,
            "running":       self._running,
        }

    def get_service(self, camera_id: str) -> CameraService | None:
        return self._services.get(camera_id)

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _start_service(self, cam: Camera) -> None:
        """Add the camera to the Multiprocessing Engine Manager."""
        from inference_engine.engine_manager import engine_manager
        
        rtsp_url = self._inject_credentials(cam)
        engine_manager.add_camera(cam.id, rtsp_url)
        
        # We store a mock service to satisfy existing status/health checks
        # Phase 10 will replace this with Prometheus metrics
        class MockService:
            class Health:
                state = StreamState.ACTIVE
            health = Health()
            def get_health(self):
                return {"state": self.health.state.value}
            async def stop(self):
                engine_manager.remove_camera(cam.id)
                
        self._services[cam.id] = MockService()
        
    @staticmethod
    def _inject_credentials(cam: Camera) -> str:
        """
        Inject username/password into the RTSP URL if stored separately.
        Handles: rtsp://host/path → rtsp://user:pass@host/path
        """
        url = cam.rtsp_url
        if cam.username and cam.password:
            if "://" in url and "@" not in url:
                proto, rest = url.split("://", 1)
                url = f"{proto}://{cam.username}:{cam.password}@{rest}"
        return url


# ── Global singleton ───────────────────────────────────────────────────────────
camera_manager = CameraManager()
