"""
engine_manager.py — Multiprocessing Orchestrator.

Manages the lifecycle of CaptureWorkers and InferenceWorkers.
Uses 3 queues:
  frame_queue:     CaptureWorker → InferenceWorker (JPEG bytes)
  annotated_queue: InferenceWorker → EngineManager (JPEG bytes for MJPEG)
  event_queue:     CaptureWorker + InferenceWorker → EngineManager (state/detection dicts)

Bridges blocking mp.Queue to asyncio.Queue for FastAPI consumption.
"""

import asyncio
import multiprocessing as mp
from typing import Dict, Optional
import time
import logging

logger = logging.getLogger("retailai.cv.manager")

from .capture_worker import CaptureWorker
from .inference_worker import InferenceWorker


class EngineManager:
    def __init__(self):
        self._running = False

        # Inter-process queues
        self.frame_queue = None       # Raw JPEG: CaptureWorker → InferenceWorker
        self.annotated_queue = None   # Annotated JPEG: InferenceWorker → EngineManager (MJPEG)
        self.event_queue = None       # State/detection events: Workers → EngineManager

        self.inference_worker: Optional[InferenceWorker] = None
        self.capture_workers: Dict[str, CaptureWorker] = {}

        # asyncio bridge
        self._async_event_queue: Optional[asyncio.Queue] = None
        self._bridge_task = None
        self._annotated_bridge_task = None

        # Latest JPEG bytes per camera for MJPEG /video_feed endpoint
        self.latest_frames: Dict[str, bytes] = {}
        self.camera_states: Dict[str, str] = {}

    def start(self):
        if self._running:
            return

        logger.info("[EngineManager] Starting multiprocessing CV architecture...")

        # Spawn context is required for CUDA / PyTorch child processes on all platforms
        ctx = mp.get_context('spawn')

        self.frame_queue = ctx.Queue(maxsize=5)
        self.annotated_queue = ctx.Queue(maxsize=5)
        self.event_queue = ctx.Queue(maxsize=1000)

        # InferenceWorker: reads from frame_queue, writes to annotated_queue + event_queue
        self.inference_worker = InferenceWorker(
            input_queue=self.frame_queue,
            annotated_queue=self.annotated_queue,
            event_queue=self.event_queue,
        )
        self.inference_worker.start()
        logger.info(f"[EngineManager] InferenceWorker started (PID={self.inference_worker.pid})")

        self._running = True

        # Async queues and bridge tasks will be started in start_async()
        # (must be called after the asyncio event loop is running)
        self._async_event_queue = asyncio.Queue()

    async def start_async(self):
        """Starts async bridge tasks. Must be called from within the asyncio event loop."""
        self._bridge_task = asyncio.create_task(self._event_queue_bridge())
        self._annotated_bridge_task = asyncio.create_task(self._annotated_queue_bridge())
        logger.info("[EngineManager] Async bridge tasks started.")

    async def stop(self):
        self._running = False
        logger.info("[EngineManager] Stopping all workers...")

        for camera_id, worker in list(self.capture_workers.items()):
            try:
                worker.stop()
                worker.join(timeout=2.0)
                if worker.is_alive():
                    worker.terminate()
                logger.info(f"[EngineManager] CaptureWorker for {camera_id} stopped.")
            except Exception as e:
                logger.warning(f"[EngineManager] Error stopping CaptureWorker {camera_id}: {e}")
        self.capture_workers.clear()

        if self.inference_worker:
            try:
                self.inference_worker.stop()
                self.inference_worker.join(timeout=5.0)
                if self.inference_worker.is_alive():
                    self.inference_worker.terminate()
                logger.info("[EngineManager] InferenceWorker stopped.")
            except Exception as e:
                logger.warning(f"[EngineManager] Error stopping InferenceWorker: {e}")

        if self._bridge_task:
            self._bridge_task.cancel()
        if self._annotated_bridge_task:
            self._annotated_bridge_task.cancel()

    def add_camera(self, camera_id: str, rtsp_url: str):
        """Spawns a CaptureWorker for a camera."""
        if camera_id in self.capture_workers:
            logger.info(f"[EngineManager] Camera {camera_id} already has a worker — skipping.")
            return

        logger.info(f"[EngineManager] Spawning CaptureWorker for camera {camera_id} → {rtsp_url}")
        worker = CaptureWorker(camera_id, rtsp_url, self.frame_queue, self.event_queue)
        self.capture_workers[camera_id] = worker
        self.camera_states[camera_id] = "INITIALIZING"
        worker.start()
        logger.info(f"[EngineManager] CaptureWorker started (PID={worker.pid}) for camera {camera_id}")

    def remove_camera(self, camera_id: str):
        """Stops and removes a camera's CaptureWorker."""
        worker = self.capture_workers.pop(camera_id, None)
        if worker:
            try:
                worker.stop()
                worker.join(timeout=2.0)
                if worker.is_alive():
                    worker.terminate()
            except Exception as e:
                logger.warning(f"[EngineManager] Error removing CaptureWorker {camera_id}: {e}")
            logger.info(f"[EngineManager] CaptureWorker removed for camera {camera_id}")
        self.camera_states.pop(camera_id, None)
        self.latest_frames.pop(camera_id, None)

    def get_latest_frame(self, camera_id: str) -> Optional[bytes]:
        """Returns the latest annotated JPEG frame bytes for MJPEG streaming."""
        return self.latest_frames.get(camera_id)

    def get_camera_state(self, camera_id: str) -> str:
        return self.camera_states.get(camera_id, "UNKNOWN")

    def get_diagnostics(self, camera_id: str) -> dict:
        """Returns a diagnostics snapshot for a camera."""
        worker = self.capture_workers.get(camera_id)
        return {
            "camera_id": camera_id,
            "state": self.camera_states.get(camera_id, "UNKNOWN"),
            "worker_alive": worker.is_alive() if worker else False,
            "worker_pid": worker.pid if worker else None,
            "has_latest_frame": camera_id in self.latest_frames,
            "frame_queue_size": self.frame_queue.qsize() if self.frame_queue else 0,
            "annotated_queue_size": self.annotated_queue.qsize() if self.annotated_queue else 0,
            "event_queue_size": self.event_queue.qsize() if self.event_queue else 0,
        }

    async def _event_queue_bridge(self):
        """Bridges blocking mp.Queue[event] → asyncio.Queue."""
        loop = asyncio.get_running_loop()
        logger.info("[EngineManager] Event bridge started.")

        while self._running:
            try:
                event = await loop.run_in_executor(None, self.event_queue.get)

                event_type = event.get("type")
                camera_id = event.get("camera_id")

                if event_type == "camera_state":
                    state = event.get("state", "UNKNOWN")
                    self.camera_states[camera_id] = state
                    logger.debug(f"[EngineManager] State: {camera_id} → {state}")
                    await self._async_event_queue.put(event)

                elif event_type == "detections":
                    await self._async_event_queue.put(event)

                else:
                    logger.debug(f"[EngineManager] Unknown event type: {event_type}")

            except Exception as e:
                logger.error(f"[EngineManager] Event bridge error: {e}")
                await asyncio.sleep(0.1)

    async def _annotated_queue_bridge(self):
        """Bridges blocking mp.Queue[annotated JPEG] → latest_frames dict."""
        loop = asyncio.get_running_loop()
        logger.info("[EngineManager] Annotated frame bridge started.")

        while self._running:
            try:
                item = await loop.run_in_executor(None, self.annotated_queue.get)
                camera_id, frame_ts, jpeg_bytes = item
                self.latest_frames[camera_id] = jpeg_bytes
            except Exception as e:
                logger.error(f"[EngineManager] Annotated bridge error: {e}")
                await asyncio.sleep(0.1)

    async def get_next_event(self) -> dict:
        """Consumed by EventEngine to process detections and state changes."""
        return await self._async_event_queue.get()


engine_manager = EngineManager()
