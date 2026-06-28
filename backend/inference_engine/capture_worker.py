"""
capture_worker.py — RTSP Frame Grabber with Buffer Management.

Runs as an independent thread or process per camera.
Continuously reads frames from RTSP to drain the internal OpenCV buffer.
Keeps only the most recent frame in an external Queue for zero-latency inference.
"""

import time
import cv2
import threading
import multiprocessing as mp
import numpy as np
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

class CaptureWorker:
    def __init__(self, camera_id: str, rtsp_url: str, output_queue: mp.Queue):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.output_queue = output_queue
        
        self._running = False
        self._cap = None
        self._thread = None
        self._latest_frame = None
        self._lock = threading.Lock()
        
        # Exponential backoff parameters
        self._reconnect_delay = 1.0
        self._max_delay = 30.0

    def start(self):
        """Starts the capture worker thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name=f"CaptureWorker-{self.camera_id}")
        self._thread.start()
        logger.info(f"[CaptureWorker] Started for camera {self.camera_id}")

    def stop(self):
        """Stops the capture worker gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
        logger.info(f"[CaptureWorker] Stopped for camera {self.camera_id}")

    def _connect(self) -> bool:
        """Attempts to open the RTSP stream."""
        if self._cap:
            self._cap.release()
            
        logger.info(f"[CaptureWorker] Connecting to {self.rtsp_url}...")
        
        # Optimizations to reduce latency for RTSP streams via FFmpeg backend
        # Using environment variables or standard cv2 caps if available.
        self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Force tiny buffer
        
        if not self._cap.isOpened():
            logger.error(f"[CaptureWorker] Failed to connect to {self.camera_id}")
            return False
            
        logger.info(f"[CaptureWorker] Connected successfully to {self.camera_id}")
        self._reconnect_delay = 1.0 # Reset backoff
        return True

    def _capture_loop(self):
        """Main loop: Read from stream continuously."""
        while self._running:
            if not self._cap or not self._cap.isOpened():
                success = self._connect()
                if not success:
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, self._max_delay)
                    continue

            ret, frame = self._cap.read()
            
            if not ret:
                logger.warning(f"[CaptureWorker] Stream died for {self.camera_id}. Reconnecting...")
                self._cap.release()
                continue
                
            # Frame acquired successfully
            with self._lock:
                self._latest_frame = frame
                
            # Push to the multiprocessing queue (drop if queue is full)
            self._push_to_queue()

    def _push_to_queue(self):
        """Places the latest frame in the output queue if there's space."""
        # To avoid blocking the capture thread (which causes lag), we use put_nowait
        # If the inference engine is too slow, the queue gets full, and we drop the frame here.
        with self._lock:
            frame_to_push = self._latest_frame.copy() if self._latest_frame is not None else None
            
        if frame_to_push is None:
            return
            
        try:
            # Drain the queue if full to always push the absolute latest frame
            while not self.output_queue.empty():
                try:
                    self.output_queue.get_nowait()
                except Exception:
                    pass
            
            # Send (camera_id, frame_timestamp, frame)
            self.output_queue.put_nowait((self.camera_id, time.time(), frame_to_push))
        except Exception:
            pass # Queue full or broken, drop frame and continue
