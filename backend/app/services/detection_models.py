"""
detection_models.py — Pydantic data models for the detection pipeline.

All models are immutable, serializable, and privacy-safe:
  - Only bounding box coordinates are stored (no pixel crops)
  - No face crops, no biometrics, no identity linking
  - Track IDs are ephemeral session integers, never persisted
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, computed_field, model_validator


# ── Retail Class Registry ──────────────────────────────────────────────────────

class RetailClass(IntEnum):
    """
    Unified class IDs used throughout the pipeline.

    COCO model classes (YOLOv11n default weights):
      PERSON = 0   →  COCO class 0 (person)

    Custom-model classes (fine-tuned on retail dataset):
      SHOPPING_CART     = 100  (not in COCO → requires custom weights)
      CHECKOUT_COUNTER  = 101  (not in COCO → requires custom weights)

    When using standard COCO weights, only PERSON is detected.
    Set `model_path` to your fine-tuned .pt to enable retail classes.
    """
    PERSON           = 0
    SHOPPING_CART    = 100
    CHECKOUT_COUNTER = 101


CLASS_META: dict[int, dict[str, Any]] = {
    RetailClass.PERSON: {
        "name":         "person",
        "coco_id":      0,
        "color_hex":    "#3b82f6",   # blue
        "min_conf":     0.40,
        "description":  "Customer or staff member (anonymous)",
    },
    RetailClass.SHOPPING_CART: {
        "name":         "shopping_cart",
        "coco_id":      None,        # custom class
        "color_hex":    "#10b981",   # green
        "min_conf":     0.50,
        "description":  "Shopping cart or basket",
    },
    RetailClass.CHECKOUT_COUNTER: {
        "name":         "checkout_counter",
        "coco_id":      None,        # custom class
        "color_hex":    "#f59e0b",   # amber
        "min_conf":     0.60,
        "description":  "Active checkout counter / till",
    },
}

# COCO → RetailClass mapping (for standard weights)
COCO_TO_RETAIL: dict[int, RetailClass] = {
    0: RetailClass.PERSON,
}

# Names for display
CLASS_NAMES = {rc.value: meta["name"] for rc, meta in CLASS_META.items()}


# ── Geometry ───────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    """Axis-aligned bounding box in absolute pixel coordinates."""
    x1: float = Field(description="Left edge (pixels)")
    y1: float = Field(description="Top edge (pixels)")
    x2: float = Field(description="Right edge (pixels)")
    y2: float = Field(description="Bottom edge (pixels)")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_coords(self) -> "BoundingBox":
        if self.x1 > self.x2:
            raise ValueError(f"x1 ({self.x1}) must be ≤ x2 ({self.x2})")
        if self.y1 > self.y2:
            raise ValueError(f"y1 ({self.y1}) must be ≤ y2 ({self.y2})")
        return self

    @computed_field
    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @computed_field
    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @computed_field
    @property
    def area(self) -> float:
        return self.width * self.height

    @computed_field
    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @computed_field
    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @computed_field
    @property
    def center(self) -> tuple[float, float]:
        return (self.center_x, self.center_y)

    def normalized(self, frame_w: int, frame_h: int) -> "NormalizedBBox":
        """Convert to 0-1 normalized coordinates."""
        return NormalizedBBox(
            x1=self.x1 / frame_w, y1=self.y1 / frame_h,
            x2=self.x2 / frame_w, y2=self.y2 / frame_h,
        )

    def iou(self, other: "BoundingBox") -> float:
        """Intersection over Union."""
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def to_xywh(self) -> tuple[float, float, float, float]:
        """Convert to (x_center, y_center, width, height) — YOLO format."""
        return (self.center_x, self.center_y, self.width, self.height)

    def to_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]


class NormalizedBBox(BaseModel):
    """Bounding box with coordinates in [0, 1] range."""
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)
    model_config = {"frozen": True}


# ── Detection ──────────────────────────────────────────────────────────────────

class Detection(BaseModel):
    """
    Single object detection output — the canonical pipeline event.

    Privacy guarantee: contains ONLY bounding box geometry.
    No pixel data, no face crops, no biometric features.
    """
    # Identity
    class_id:    int   = Field(description="RetailClass int value")
    class_name:  str   = Field(description="Human-readable class name")

    # Scores
    confidence:  float = Field(ge=0.0, le=1.0, description="Detection confidence")

    # Geometry
    bounding_box: BoundingBox

    # Context
    timestamp:   float  = Field(description="Unix timestamp of source frame")
    camera_id:   str    = Field(description="Source camera ID")

    # Optional enrichments
    track_id:    int | None  = Field(default=None, description="ByteTrack ephemeral ID")
    frame_idx:   int | None  = Field(default=None, description="Frame sequence number")
    zone_ids:    list[str]   = Field(default_factory=list, description="Zone IDs this detection falls within")

    model_config = {"frozen": True}

    @computed_field
    @property
    def datetime_utc(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @computed_field
    @property
    def class_color(self) -> str:
        return CLASS_META.get(self.class_id, {}).get("color_hex", "#ffffff")

    def to_dict(self) -> dict[str, Any]:
        return {
            "class":        self.class_name,
            "class_id":     self.class_id,
            "confidence":   round(self.confidence, 4),
            "bounding_box": self.bounding_box.to_list(),
            "timestamp":    self.timestamp,
            "camera_id":    self.camera_id,
            "track_id":     self.track_id,
            "zone_ids":     self.zone_ids,
        }


# ── Frame result ───────────────────────────────────────────────────────────────

class DetectionFrame(BaseModel):
    """
    All detections for a single video frame from one camera.
    This is the primary output unit of the detection pipeline.
    """
    camera_id:     str
    timestamp:     float
    frame_idx:     int
    frame_shape:   tuple[int, int]     # (height, width)
    detections:    list[Detection]
    inference_ms:  float               # Time to run model inference
    total_ms:      float               # Total processing time including pre/post

    model_config = {"frozen": True}

    @computed_field
    @property
    def person_count(self) -> int:
        return sum(1 for d in self.detections if d.class_id == RetailClass.PERSON)

    @computed_field
    @property
    def cart_count(self) -> int:
        return sum(1 for d in self.detections if d.class_id == RetailClass.SHOPPING_CART)

    @computed_field
    @property
    def total_count(self) -> int:
        return len(self.detections)

    def filter_by_class(self, *class_ids: int) -> "DetectionFrame":
        return self.model_copy(update={
            "detections": [d for d in self.detections if d.class_id in class_ids]
        })

    def filter_by_confidence(self, min_conf: float) -> "DetectionFrame":
        return self.model_copy(update={
            "detections": [d for d in self.detections if d.confidence >= min_conf]
        })

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "camera_id":    self.camera_id,
            "timestamp":    self.timestamp,
            "frame_idx":    self.frame_idx,
            "detections":   [d.to_dict() for d in self.detections],
            "person_count": self.person_count,
            "cart_count":   self.cart_count,
            "inference_ms": round(self.inference_ms, 2),
        }


# ── Batch ──────────────────────────────────────────────────────────────────────

@dataclass
class FrameBatch:
    """
    A batch of frames from multiple cameras ready for inference.
    Internal struct — not serialized.
    """
    frames:      list[np.ndarray]          # Pre-processed frames
    camera_ids:  list[str]
    timestamps:  list[float]
    frame_idxs:  list[int]
    shapes:      list[tuple[int, int]]     # Original (H, W) per frame
    queued_at:   float = field(default_factory=time.monotonic)

    @property
    def size(self) -> int:
        return len(self.frames)

    @property
    def queue_latency_ms(self) -> float:
        return (time.monotonic() - self.queued_at) * 1000


# ── Configuration ──────────────────────────────────────────────────────────────

class DetectionConfig(BaseModel):
    """Runtime configuration for the detection service."""
    model_path:        str   = "yolo11n.pt"
    device:            str   = "auto"          # auto | cpu | cuda | cuda:0 | mps
    confidence_threshold: float = Field(default=0.40, ge=0.1, le=1.0)
    iou_threshold:     float = Field(default=0.45, ge=0.1, le=1.0)
    max_detections:    int   = Field(default=100, ge=1, le=1000)
    input_size:        int   = Field(default=640, ge=320, le=1280)
    batch_size:        int   = Field(default=4,  ge=1,  le=32)
    batch_timeout_ms:  float = Field(default=50.0, ge=5.0, le=500.0)

    # Classes to detect (None = all configured retail classes)
    enabled_classes: list[int] | None = None

    # Half precision (FP16) — only valid on GPU
    half_precision: bool = False

    # Augmented inference (TTA) — slower but more accurate
    augment: bool = False

    @property
    def target_classes(self) -> list[int]:
        if self.enabled_classes is not None:
            return self.enabled_classes
        # Default: COCO person only (standard weights)
        return [RetailClass.PERSON]

    @property
    def resolved_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"
