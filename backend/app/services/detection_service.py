"""
detection_service.py — YOLOv11n inference engine.

Responsibilities:
  - Load & warm-up the YOLO model (GPU/CPU/MPS auto-detection)
  - Pre-process frames for batched inference
  - Run async inference offloaded to a dedicated thread
  - Post-process raw YOLO output → Detection objects
  - Apply per-class confidence thresholds
  - Expose metrics (throughput, latency, GPU memory)

Privacy:
  - Only bounding boxes are returned (no pixel crops extracted)
  - class_id=0 (person) detected with box only — zero biometrics
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

from app.core.logging import get_logger
from app.services.detection_models import (
    BoundingBox, COCO_TO_RETAIL, CLASS_META,
    Detection, DetectionConfig, DetectionFrame,
    FrameBatch, RetailClass,
)

logger = get_logger(__name__)


class InferenceMetrics:
    """Rolling metrics for monitoring inference performance."""
    def __init__(self, window: int = 100):
        self._window       = window
        self._latencies:   list[float] = []
        self._throughputs: list[float] = []
        self.total_frames  = 0
        self.total_batches = 0
        self.total_detections = 0
        self.errors        = 0

    def record(self, batch_size: int, inference_ms: float) -> None:
        self.total_frames     += batch_size
        self.total_batches    += 1
        fps = (batch_size / inference_ms) * 1000 if inference_ms > 0 else 0
        self._latencies.append(inference_ms)
        self._throughputs.append(fps)
        if len(self._latencies) > self._window:
            self._latencies.pop(0)
            self._throughputs.pop(0)

    @property
    def avg_latency_ms(self) -> float:
        return sum(self._latencies) / len(self._latencies) if self._latencies else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if not self._latencies:
            return 0.0
        s = sorted(self._latencies)
        return s[int(len(s) * 0.95)]

    @property
    def avg_throughput_fps(self) -> float:
        return sum(self._throughputs) / len(self._throughputs) if self._throughputs else 0.0

    def to_dict(self) -> dict:
        return {
            "total_frames":    self.total_frames,
            "total_batches":   self.total_batches,
            "total_detections": self.total_detections,
            "avg_latency_ms":  round(self.avg_latency_ms, 2),
            "p95_latency_ms":  round(self.p95_latency_ms, 2),
            "avg_fps":         round(self.avg_throughput_fps, 2),
            "errors":          self.errors,
        }


class DetectionService:
    """
    Production YOLOv11n inference service.

    Usage:
        svc = DetectionService(DetectionConfig())
        await svc.initialize()

        frames = [frame_np_array]           # uint8 BGR, HWC
        results = await svc.infer_batch(batch)

        await svc.shutdown()

    The service is safe to share across cameras — the YOLO model
    is loaded once and inference calls are serialized through the
    thread executor (GIL-aware: torch releases GIL during inference).
    """

    def __init__(self, config: DetectionConfig | None = None):
        self.config   = config or DetectionConfig()
        self._model   = None          # ultralytics YOLO
        self._device  = "cpu"
        self._ready   = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yolo-infer")
        self.metrics  = InferenceMetrics()
        self._warmup_done = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Load model and warm up. Call once at app startup."""
        if self._ready:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._load_model)
        await loop.run_in_executor(self._executor, self._warmup)
        self._ready = True
        logger.info(
            "DetectionService ready",
            extra={
                "device":     self._device,
                "model":      self.config.model_path,
                "input_size": self.config.input_size,
                "classes":    self.config.target_classes,
            },
        )

    async def shutdown(self) -> None:
        self._ready = False
        self._executor.shutdown(wait=False)
        logger.info("DetectionService shut down")

    # ── Public inference API ───────────────────────────────────────────────────

    async def infer_single(
        self,
        frame: np.ndarray,
        camera_id: str,
        timestamp: float | None = None,
        frame_idx: int = 0,
    ) -> DetectionFrame:
        """Infer on a single frame. Wraps infer_batch for convenience."""
        batch = FrameBatch(
            frames=[frame],
            camera_ids=[camera_id],
            timestamps=[timestamp or time.time()],
            frame_idxs=[frame_idx],
            shapes=[frame.shape[:2]],
        )
        results = await self.infer_batch(batch)
        return results[0]

    async def infer_batch(self, batch: FrameBatch) -> list[DetectionFrame]:
        """
        Run batched inference on multiple frames asynchronously.
        Frames can be from different cameras.
        Returns one DetectionFrame per input frame.
        """
        if not self._ready:
            raise RuntimeError("DetectionService not initialized. Call await svc.initialize() first.")

        loop   = asyncio.get_running_loop()
        t_start = time.perf_counter()

        results = await loop.run_in_executor(
            self._executor,
            lambda: self._run_inference(batch),
        )

        total_ms = (time.perf_counter() - t_start) * 1000
        logger.debug(
            "Batch inference complete",
            extra={
                "batch_size": batch.size,
                "total_ms":   round(total_ms, 2),
                "queue_lag_ms": round(batch.queue_latency_ms, 2),
            },
        )
        return results

    # ── Model loading ──────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Blocking — run in executor."""
        try:
            from ultralytics import YOLO
        except ImportError:
            raise RuntimeError(
                "ultralytics not installed. Run: pip install ultralytics"
            )

        self._device = self.config.resolved_device
        logger.info(
            "Loading YOLO model",
            extra={"model": self.config.model_path, "device": self._device},
        )
        t0 = time.perf_counter()
        self._model = YOLO(self.config.model_path)
        self._model.to(self._device)

        if self.config.half_precision and self._device != "cpu":
            self._model.model.half()

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("Model loaded", extra={"load_ms": round(elapsed, 1)})

    def _warmup(self) -> None:
        """Run 3 dummy inferences to prime CUDA/memory allocations."""
        if self._model is None:
            return
        dummy = np.zeros(
            (self.config.input_size, self.config.input_size, 3), dtype=np.uint8
        )
        logger.info("Warming up model…")
        for _ in range(3):
            self._model.predict(
                source=dummy,
                imgsz=self.config.input_size,
                conf=self.config.confidence_threshold,
                verbose=False,
                device=self._device,
            )
        self._warmup_done = True
        logger.info("Model warm-up complete")

    # ── Inference ──────────────────────────────────────────────────────────────

    def _run_inference(self, batch: FrameBatch) -> list[DetectionFrame]:
        """
        Blocking inference — runs in the thread executor.
        Handles pre-processing, inference, and post-processing.
        """
        t_infer_start = time.perf_counter()

        # Build list of frames for YOLO (accepts list of np arrays)
        try:
            raw_results = self._model.predict(
                source=batch.frames,
                imgsz=self.config.input_size,
                conf=self.config.confidence_threshold,
                iou=self.config.iou_threshold,
                max_det=self.config.max_detections,
                classes=self._coco_class_filter(),
                augment=self.config.augment,
                verbose=False,
                device=self._device,
                stream=False,
            )
        except Exception as exc:
            self.metrics.errors += 1
            logger.error("YOLO inference failed", extra={"error": str(exc)})
            return [self._empty_frame(batch, i) for i in range(batch.size)]

        inference_ms = (time.perf_counter() - t_infer_start) * 1000
        self.metrics.record(batch.size, inference_ms)

        detection_frames: list[DetectionFrame] = []
        t_total_start = time.perf_counter()

        for i, result in enumerate(raw_results):
            detections = self._parse_result(
                result=result,
                camera_id=batch.camera_ids[i],
                timestamp=batch.timestamps[i],
                frame_idx=batch.frame_idxs[i],
                orig_shape=batch.shapes[i],
            )
            self.metrics.total_detections += len(detections)

            detection_frames.append(DetectionFrame(
                camera_id=batch.camera_ids[i],
                timestamp=batch.timestamps[i],
                frame_idx=batch.frame_idxs[i],
                frame_shape=batch.shapes[i],
                detections=detections,
                inference_ms=inference_ms / batch.size,   # per-frame share
                total_ms=(time.perf_counter() - t_total_start) * 1000,
            ))

        return detection_frames

    def _parse_result(
        self,
        result: Any,
        camera_id: str,
        timestamp: float,
        frame_idx: int,
        orig_shape: tuple[int, int],
    ) -> list[Detection]:
        """Convert a YOLO result object to Detection list."""
        detections: list[Detection] = []

        if result.boxes is None or len(result.boxes) == 0:
            return detections

        boxes = result.boxes
        # boxes.xyxy  → tensor (N, 4) in pixel coords
        # boxes.conf  → tensor (N,)
        # boxes.cls   → tensor (N,)

        xyxy   = boxes.xyxy.cpu().numpy()
        confs  = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)

        for j in range(len(xyxy)):
            coco_id    = int(classes[j])
            confidence = float(confs[j])

            # Map COCO → RetailClass
            retail_class = COCO_TO_RETAIL.get(coco_id)
            if retail_class is None:
                # Could be a custom class from fine-tuned model
                if coco_id in [rc.value for rc in RetailClass]:
                    retail_class = RetailClass(coco_id)
                else:
                    continue  # Unknown class — skip

            # Per-class confidence threshold
            class_min_conf = CLASS_META.get(retail_class.value, {}).get("min_conf", 0.40)
            if confidence < class_min_conf:
                continue

            x1, y1, x2, y2 = float(xyxy[j][0]), float(xyxy[j][1]), float(xyxy[j][2]), float(xyxy[j][3])

            # Clamp to frame bounds
            h, w = orig_shape
            x1 = max(0.0, min(x1, w))
            y1 = max(0.0, min(y1, h))
            x2 = max(0.0, min(x2, w))
            y2 = max(0.0, min(y2, h))

            if x2 <= x1 or y2 <= y1:
                continue

            detections.append(Detection(
                class_id=retail_class.value,
                class_name=retail_class.name.lower(),
                confidence=confidence,
                bounding_box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                timestamp=timestamp,
                camera_id=camera_id,
                frame_idx=frame_idx,
            ))

        return detections

    def _coco_class_filter(self) -> list[int] | None:
        """
        Returns COCO class IDs to filter by, or None for all classes.
        Custom retail classes (>99) won't be filtered here — they're
        handled by the custom model's own class mapping.
        """
        coco_ids = [
            coco_id
            for retail_id in self.config.target_classes
            for coco_id, retail in COCO_TO_RETAIL.items()
            if retail.value == retail_id
        ]
        return coco_ids if coco_ids else None

    @staticmethod
    def _empty_frame(batch: FrameBatch, idx: int) -> DetectionFrame:
        return DetectionFrame(
            camera_id=batch.camera_ids[idx],
            timestamp=batch.timestamps[idx],
            frame_idx=batch.frame_idxs[idx],
            frame_shape=batch.shapes[idx],
            detections=[],
            inference_ms=0.0,
            total_ms=0.0,
        )

    # ── Status ─────────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready

    def get_status(self) -> dict[str, Any]:
        gpu_info = self._get_gpu_info()
        return {
            "ready":       self._ready,
            "device":      self._device,
            "model":       self.config.model_path,
            "input_size":  self.config.input_size,
            "half":        self.config.half_precision,
            "batch_size":  self.config.batch_size,
            "classes":     [
                {"id": cid, "name": CLASS_META.get(cid, {}).get("name", str(cid))}
                for cid in self.config.target_classes
            ],
            "metrics":     self.metrics.to_dict(),
            "gpu":         gpu_info,
        }

    @staticmethod
    def _get_gpu_info() -> dict[str, Any] | None:
        try:
            import torch
            if not torch.cuda.is_available():
                return None
            idx = torch.cuda.current_device()
            return {
                "name":           torch.cuda.get_device_name(idx),
                "memory_total_mb": round(torch.cuda.get_device_properties(idx).total_memory / 1024**2),
                "memory_used_mb":  round(torch.cuda.memory_allocated(idx) / 1024**2),
                "memory_free_mb":  round(torch.cuda.memory_reserved(idx) / 1024**2),
            }
        except Exception:
            return None


# ── Singleton factory ──────────────────────────────────────────────────────────

_service_instance: DetectionService | None = None


def get_detection_service(config: DetectionConfig | None = None) -> DetectionService:
    global _service_instance
    if _service_instance is None:
        _service_instance = DetectionService(config)
    return _service_instance
