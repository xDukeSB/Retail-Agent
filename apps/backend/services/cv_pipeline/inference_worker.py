"""
inference_worker.py — YOLOv11 + ByteTrack Multiprocessing Worker.

Runs in a separate process. Pulls JPEG-encoded frames from the capture queue,
decodes them, performs hardware-accelerated YOLO inference + ByteTrack identity
association, JPEG-encodes the annotated frame, and pushes results to the event queue.

Architecture:
  CaptureWorker → frame_queue (JPEG bytes) → InferenceWorker → event_queue (events + JPEG frames)
"""

import time
import multiprocessing as mp
from typing import Dict, Any, List, Optional
import traceback
import logging

import cv2
import numpy as np

try:
    from ultralytics import YOLO
    import torch
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    torch = None
    ULTRALYTICS_AVAILABLE = False

logger = logging.getLogger("retailai.cv.inference")


class InferenceWorker(mp.Process):
    """
    Consumes JPEG bytes from the frame queue, runs YOLO + ByteTrack,
    and emits annotated JPEG frames + detection events to the event queue.
    """

    def __init__(self, input_queue: mp.Queue, annotated_queue: mp.Queue, event_queue: mp.Queue):
        super().__init__(name="InferenceWorker", daemon=True)
        self.input_queue = input_queue
        self.annotated_queue = annotated_queue   # For MJPEG streaming
        self.event_queue = event_queue           # For state events + detections
        self._running = mp.Event()
        self.model = None
        self._frame_counts: Dict[str, int] = {}
        self._inference_fps: Dict[str, float] = {}

    def _emit_event(self, event: dict):
        try:
            self.event_queue.put_nowait(event)
        except Exception:
            pass  # Queue full — drop event, never block inference

    def _emit_state(self, camera_id: str, state: str, details: str = ""):
        self._emit_event({
            "type": "camera_state",
            "camera_id": camera_id,
            "state": state,
            "details": details,
            "timestamp": time.time()
        })

    def run(self):
        """Process execution entrypoint."""
        self._running.set()
        logger.info("[InferenceWorker] Process started. Initializing YOLO + ByteTrack...")

        if not ULTRALYTICS_AVAILABLE:
            logger.error(
                "[InferenceWorker] FATAL: ultralytics is not installed.\n"
                "  Fix: pip install ultralytics\n"
                "  Halting inference worker."
            )
            return

        # ── Model Initialization ────────────────────────────────────────────────
        try:
            device = "cuda" if (torch and torch.cuda.is_available()) else "cpu"
            logger.info(f"[InferenceWorker] Loading YOLOv8n on device: {device}")
            self.model = YOLO("yolov8n.pt")
            self.model.to(device)
            logger.info(f"[InferenceWorker] Model ready on {device}. Entering inference loop.")
        except Exception as e:
            logger.error(
                f"[InferenceWorker] Model load FAILED:\n"
                f"  Error:    {e}\n"
                f"  Stage:    Model Initialization\n"
                f"  Trace:    {traceback.format_exc()}\n"
                f"  Recovery: Exiting — fix model path or install ultralytics."
            )
            return

        # ── Inference Loop ───────────────────────────────────────────────────────
        while self._running.is_set():
            try:
                item = self.input_queue.get(timeout=1.0)
            except Exception:
                continue  # Timeout — no frames yet, keep waiting

            camera_id, frame_ts, jpeg_bytes = item

            # ── Decode JPEG → numpy ──────────────────────────────────────────────
            try:
                np_arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is None or frame.size == 0:
                    logger.warning(f"[InferenceWorker] cv2.imdecode() returned None for {camera_id}")
                    continue
            except Exception as e:
                logger.error(f"[InferenceWorker] JPEG decode failed for {camera_id}: {e}")
                continue

            # ── YOLO + ByteTrack Inference ───────────────────────────────────────
            try:
                start_time = time.time()

                results = self.model.track(
                    source=frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    verbose=False,
                    classes=[0],  # Person class only
                )

                inference_ms = (time.time() - start_time) * 1000
                fps = 1000.0 / max(inference_ms, 1)

                detections = self._parse_results(results)

                # Update frame count per camera
                self._frame_counts[camera_id] = self._frame_counts.get(camera_id, 0) + 1
                self._inference_fps[camera_id] = fps

                # Emit inference-running state
                self._emit_state(camera_id, "INFERENCE RUNNING",
                                 f"FPS:{fps:.1f} Detections:{len(detections)}")

                # Emit detection events
                self._emit_event({
                    "type": "detections",
                    "camera_id": camera_id,
                    "timestamp": frame_ts,
                    "inference_time_ms": inference_ms,
                    "detections": detections,
                    "frame_count": self._frame_counts[camera_id],
                })

                # ── Annotate frame and push to MJPEG queue ───────────────────────
                if len(results) > 0:
                    annotated_frame = results[0].plot()
                else:
                    annotated_frame = frame  # No detections, stream original

                # JPEG-encode before inter-process transfer
                ret, buf = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    annotated_bytes = buf.tobytes()
                    # Drain old frames to stay real-time
                    while not self.annotated_queue.empty():
                        try:
                            self.annotated_queue.get_nowait()
                        except Exception:
                            break
                    try:
                        self.annotated_queue.put_nowait((camera_id, frame_ts, annotated_bytes))
                    except Exception:
                        pass  # Queue full — drop frame

            except Exception as e:
                logger.error(
                    f"[InferenceWorker] Inference FAILED:\n"
                    f"  Camera:   {camera_id}\n"
                    f"  Error:    {e}\n"
                    f"  Stage:    YOLO Inference\n"
                    f"  Trace:    {traceback.format_exc()}\n"
                    f"  Recovery: Dropping frame, continuing."
                )
                self._emit_state(camera_id, "DECODER ERROR", str(e))

    def stop(self):
        """Signal the process to stop."""
        self._running.clear()
        logger.info("[InferenceWorker] Stop signal sent.")

    def _parse_results(self, results) -> List[Dict[str, Any]]:
        """Extracts bounding boxes and ByteTrack IDs from ultralytics results."""
        detections = []
        for result in results:
            if result.boxes is None:
                continue
                
            orig_h, orig_w = result.orig_shape
            
            # ByteTrack may not assign IDs on first frame — handle gracefully
            boxes = result.boxes.xyxy.cpu().numpy() if result.boxes.xyxy is not None else []
            track_ids = result.boxes.id.cpu().numpy() if result.boxes.id is not None else [None] * len(boxes)
            confidences = result.boxes.conf.cpu().numpy() if result.boxes.conf is not None else [0.0] * len(boxes)

            for box, track_id, conf in zip(boxes, track_ids, confidences):
                x1, y1, x2, y2 = map(float, box)
                
                cx = float((x1 + x2) / 2) / orig_w
                cy = float((y1 + y2) / 2) / orig_h
                
                detections.append({
                    "track_id": int(track_id) if track_id is not None else -1,
                    "confidence": float(conf),
                    "bbox": [x1, y1, x2, y2],
                    "centroid": [cx, cy]
                })
        return detections
