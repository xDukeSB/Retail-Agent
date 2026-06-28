"""
engine_manager.py — Multiprocessing Orchestrator.

Manages the lifecycle of CaptureWorkers and InferenceWorkers.
Provides an async queue for the FastAPI backend to consume pure analytical events
without blocking the main thread.
"""

import asyncio
import multiprocessing as mp
from typing import Dict

from app.core.logging import get_logger
from inference_engine.capture_worker import CaptureWorker
from inference_engine.inference_worker import InferenceWorker

logger = get_logger(__name__)

class EngineManager:
    def __init__(self):
        self._running = False
        
        # mp.Queue for inter-process communication
        self.frame_queue = None
        self.event_queue = None
        
        self.inference_worker = None
        self.capture_workers: Dict[str, CaptureWorker] = {}
        
        # To bridge mp.Queue to asyncio
        self._async_event_queue = None
        self._bridge_task = None

    def start(self):
        if self._running:
            return
            
        logger.info("[EngineManager] Starting Multiprocessing Architecture...")
        
        # Use Spawn context for clean process boundaries (crucial for CUDA/PyTorch)
        ctx = mp.get_context('spawn')
        
        # maxsize=5 prevents massive buffer bloat if inference is slow
        self.frame_queue = ctx.Queue(maxsize=5)
        # Larger maxsize for events since they are just lightweight JSON dicts
        self.event_queue = ctx.Queue(maxsize=1000)
        
        # Start Inference Node
        self.inference_worker = InferenceWorker(self.frame_queue, self.event_queue)
        self.inference_worker.start()
        
        self._running = True
        
        # Start the async bridge
        self._async_event_queue = asyncio.Queue()
        self._bridge_task = asyncio.create_task(self._queue_bridge())

    async def stop(self):
        self._running = False
        logger.info("[EngineManager] Stopping workers...")
        
        # Stop captures
        for worker in self.capture_workers.values():
            worker.stop()
        self.capture_workers.clear()
        
        # Stop inference
        if self.inference_worker:
            self.inference_worker.stop()
            self.inference_worker.join(timeout=3.0)
            if self.inference_worker.is_alive():
                self.inference_worker.terminate()
                
        # Stop bridge
        if self._bridge_task:
            self._bridge_task.cancel()

    def add_camera(self, camera_id: str, rtsp_url: str):
        """Spawns a new capture thread for a camera."""
        if camera_id in self.capture_workers:
            return
            
        worker = CaptureWorker(camera_id, rtsp_url, self.frame_queue)
        self.capture_workers[camera_id] = worker
        worker.start()

    def remove_camera(self, camera_id: str):
        """Stops and removes a camera's capture thread."""
        worker = self.capture_workers.pop(camera_id, None)
        if worker:
            worker.stop()

    async def _queue_bridge(self):
        """Bridges blocking mp.Queue to non-blocking asyncio.Queue."""
        loop = asyncio.get_running_loop()
        from app.core.metrics import inference_fps, total_detections, inference_latency_ms
        import time
        
        while self._running:
            try:
                # Run the blocking get() in a threadpool
                event = await loop.run_in_executor(None, self.event_queue.get)
                
                # Update Prometheus Metrics
                cam_id = event.get("camera_id", "unknown")
                detections = event.get("detections", [])
                frame_ts = event.get("timestamp", time.time())
                
                latency = (time.time() - frame_ts) * 1000
                inference_latency_ms.labels(camera_id=cam_id).observe(latency)
                total_detections.labels(camera_id=cam_id, class_name='person').inc(len(detections))
                
                await self._async_event_queue.put(event)
            except Exception:
                await asyncio.sleep(0.1)

    async def get_next_event(self) -> dict:
        """Consumed by the Analytics Engine to process detections."""
        return await self._async_event_queue.get()

engine_manager = EngineManager()
