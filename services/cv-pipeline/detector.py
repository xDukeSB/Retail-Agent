"""
YOLOv11n person detector.
Only processes class 0 (person) — no faces, no biometrics.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("cv-pipeline.detector")


@dataclass
class Detection:
    """A single person detection — bounding box only, no biometric data."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def centroid(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def centroid_normalized(self) -> Tuple[float, float]:
        """Returns centroid as 0-1 normalized (requires frame dimensions)."""
        return self.centroid  # normalized by detector

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def to_xyxy_array(self) -> np.ndarray:
        return np.array([self.x1, self.y1, self.x2, self.y2, self.confidence])


class PersonDetector:
    """
    Wraps YOLOv11n for person-only detection.
    Privacy: only class 0 (person) is ever processed.
    """

    def __init__(self, model_path: str, confidence: float, device: str):
        self.model_path = model_path
        self.confidence = confidence
        self.device = device
        self._model = None
        logger.info(f"PersonDetector init — model: {model_path}, device: {device}")

    def load(self):
        """Lazy-load YOLO model."""
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            self._model.to(self.device)
            logger.info("YOLO model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run person detection on a frame.
        Returns list of Detection objects (no images stored, no faces cropped).
        """
        if self._model is None:
            raise RuntimeError("Model not loaded — call load() first")

        h, w = frame.shape[:2]
        results = self._model.predict(
            frame,
            conf=self.confidence,
            classes=[0],  # ← ONLY person class — privacy guarantee
            verbose=False,
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                # Normalize to 0-1
                detections.append(Detection(
                    x1=x1 / w, y1=y1 / h,
                    x2=x2 / w, y2=y2 / h,
                    confidence=conf,
                ))

        return detections
