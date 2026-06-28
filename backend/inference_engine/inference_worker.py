"""
inference_worker.py — YOLOv11 + ByteTrack Multiprocessing Worker.

Runs in a separate process. Pulls frames from the capture queue,
performs hardware-accelerated YOLO inference and ByteTrack identity association,
and pushes lightweight JSON-like event data to the output queue.
"""

import time
import multiprocessing as mp
from typing import Dict, Any, List

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None # handled dynamically

from app.core.logging import get_logger

logger = get_logger(__name__)

class InferenceWorker(mp.Process):
    def __init__(self, input_queue: mp.Queue, output_queue: mp.Queue):
        super().__init__(name="InferenceWorker")
        self.input_queue = input_queue
        self.output_queue = output_queue
        self._running = mp.Event()
        self.model = None

    def run(self):
        """Process execution entrypoint."""
        self._running.set()
        logger.info("[InferenceWorker] Initializing YOLOv11 and ByteTrack...")
        
        if YOLO is None:
            logger.error("[InferenceWorker] Ultralytics is not installed. Halting.")
            return

        try:
            # ultralytics natively supports ByteTrack by passing tracker="bytetrack.yaml"
            self.model = YOLO("yolov8n.pt") # YOLOv8/11 nano model
            logger.info("[InferenceWorker] Model loaded successfully.")
        except Exception as e:
            logger.error(f"[InferenceWorker] Failed to load model: {e}")
            return

        while self._running.is_set():
            try:
                # Wait for a frame (timeout allows checking _running flag)
                item = self.input_queue.get(timeout=1.0)
            except Exception:
                continue
                
            camera_id, frame_ts, frame = item
            
            try:
                # Run inference + tracking
                # persist=True ensures tracking IDs are maintained across frames
                # verbose=False prevents console spam
                results = self.model.track(
                    source=frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    verbose=False,
                    classes=[0] # Only track class 0 (Person) for visitors
                )
                
                detections = self._parse_results(results)
                
                # Push to output queue (to be consumed by FastAPI Analytics Engine)
                self.output_queue.put_nowait({
                    "camera_id": camera_id,
                    "timestamp": frame_ts,
                    "detections": detections
                })
                
            except Exception as e:
                logger.error(f"[InferenceWorker] Inference failed: {e}")

    def stop(self):
        """Signal the process to stop."""
        self._running.clear()

    def _parse_results(self, results) -> List[Dict[str, Any]]:
        """Extract bounding boxes and track IDs from ultralytics results."""
        detections = []
        for result in results:
            if result.boxes is None or result.boxes.id is None:
                continue
                
            boxes = result.boxes.xyxy.cpu().numpy()
            track_ids = result.boxes.id.cpu().numpy()
            confidences = result.boxes.conf.cpu().numpy()
            
            for box, track_id, conf in zip(boxes, track_ids, confidences):
                x1, y1, x2, y2 = map(float, box)
                detections.append({
                    "track_id": int(track_id),
                    "confidence": float(conf),
                    "bbox": [x1, y1, x2, y2],
                    "centroid": [float((x1 + x2) / 2), float((y1 + y2) / 2)]
                })
        return detections
