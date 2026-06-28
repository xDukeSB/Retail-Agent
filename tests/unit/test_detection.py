"""
Unit tests for the Detection Service.

Tests: BoundingBox geometry, Detection models, DetectionFrame aggregation,
DetectionConfig device resolution, class registry correctness.
No GPU or ultralytics required — inference path is mocked.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ── Mock heavy ML deps ────────────────────────────────────────────────────────
for mod in ["torch", "ultralytics", "cv2"]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

import numpy as np

from app.services.detection_models import (
    BoundingBox, COCO_TO_RETAIL, CLASS_META,
    Detection, DetectionConfig, DetectionFrame,
    FrameBatch, NormalizedBBox, RetailClass,
)


# ── BoundingBox ───────────────────────────────────────────────────────────────

class TestBoundingBox:
    def test_dimensions(self):
        box = BoundingBox(x1=10, y1=20, x2=110, y2=120)
        assert box.width  == 100
        assert box.height == 100
        assert box.area   == 10_000

    def test_center(self):
        box = BoundingBox(x1=0, y1=0, x2=200, y2=100)
        assert box.center_x == 100
        assert box.center_y == 50

    def test_invalid_coords_raise(self):
        with pytest.raises(Exception):
            BoundingBox(x1=200, y1=0, x2=100, y2=100)  # x1 > x2

    def test_normalization(self):
        box  = BoundingBox(x1=320, y1=240, x2=640, y2=480)
        norm = box.normalized(frame_w=640, frame_h=480)
        assert isinstance(norm, NormalizedBBox)
        assert abs(norm.x1 - 0.5) < 1e-6
        assert abs(norm.y1 - 0.5) < 1e-6
        assert abs(norm.x2 - 1.0) < 1e-6

    def test_iou_identical(self):
        box = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        assert abs(box.iou(box) - 1.0) < 1e-6

    def test_iou_no_overlap(self):
        a = BoundingBox(x1=0,   y1=0,   x2=50,  y2=50)
        b = BoundingBox(x1=100, y1=100, x2=150, y2=150)
        assert box.iou(b) == 0.0 if False else a.iou(b) == 0.0

    def test_iou_partial_overlap(self):
        a = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        b = BoundingBox(x1=50, y1=50, x2=150, y2=150)
        iou = a.iou(b)
        assert 0 < iou < 1

    def test_to_xywh(self):
        box = BoundingBox(x1=10, y1=20, x2=110, y2=70)
        cx, cy, w, h = box.to_xywh()
        assert cx == 60
        assert cy == 45
        assert w  == 100
        assert h  == 50

    def test_to_list(self):
        box = BoundingBox(x1=1, y1=2, x2=3, y2=4)
        assert box.to_list() == [1.0, 2.0, 3.0, 4.0]

    def test_immutable(self):
        box = BoundingBox(x1=0, y1=0, x2=10, y2=10)
        with pytest.raises(Exception):
            box.x1 = 999  # type: ignore


# ── Detection ─────────────────────────────────────────────────────────────────

class TestDetection:
    def _make(self, class_id=0, conf=0.85, camera_id="cam-1") -> Detection:
        return Detection(
            class_id=class_id,
            class_name="person",
            confidence=conf,
            bounding_box=BoundingBox(x1=10, y1=10, x2=200, y2=400),
            timestamp=1_700_000_000.0,
            camera_id=camera_id,
        )

    def test_fields_set(self):
        d = self._make()
        assert d.class_id  == 0
        assert d.class_name == "person"
        assert d.confidence == 0.85
        assert d.camera_id  == "cam-1"

    def test_to_dict_structure(self):
        d = self._make()
        result = d.to_dict()
        assert result["class"]      == "person"
        assert result["class_id"]   == 0
        assert result["camera_id"]  == "cam-1"
        assert "bounding_box"       in result
        assert "timestamp"          in result
        assert "confidence"         in result

    def test_datetime_utc(self):
        d = self._make()
        assert d.datetime_utc is not None
        assert d.datetime_utc.tzinfo is not None

    def test_class_color_present(self):
        d = self._make(class_id=RetailClass.PERSON)
        assert d.class_color.startswith("#")

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            self._make(conf=1.5)
        with pytest.raises(Exception):
            self._make(conf=-0.1)


# ── DetectionFrame ────────────────────────────────────────────────────────────

class TestDetectionFrame:
    def _frame(self, detections=None) -> DetectionFrame:
        return DetectionFrame(
            camera_id="cam-1",
            timestamp=1_700_000_000.0,
            frame_idx=42,
            frame_shape=(480, 640),
            detections=detections or [],
            inference_ms=12.3,
            total_ms=15.0,
        )

    def _det(self, class_id: int, conf: float = 0.8) -> Detection:
        return Detection(
            class_id=class_id,
            class_name=RetailClass(class_id).name.lower() if class_id in [rc.value for rc in RetailClass] else "unknown",
            confidence=conf,
            bounding_box=BoundingBox(x1=0, y1=0, x2=100, y2=100),
            timestamp=1_700_000_000.0,
            camera_id="cam-1",
        )

    def test_person_count(self):
        frame = self._frame([
            self._det(RetailClass.PERSON),
            self._det(RetailClass.PERSON),
            self._det(RetailClass.SHOPPING_CART),
        ])
        assert frame.person_count == 2
        assert frame.cart_count   == 1
        assert frame.total_count  == 3

    def test_empty_frame(self):
        frame = self._frame()
        assert frame.person_count == 0
        assert frame.total_count  == 0

    def test_filter_by_class(self):
        frame = self._frame([
            self._det(RetailClass.PERSON),
            self._det(RetailClass.SHOPPING_CART),
        ])
        filtered = frame.filter_by_class(RetailClass.PERSON)
        assert len(filtered.detections) == 1
        assert filtered.detections[0].class_id == RetailClass.PERSON

    def test_filter_by_confidence(self):
        frame = self._frame([
            self._det(RetailClass.PERSON, conf=0.90),
            self._det(RetailClass.PERSON, conf=0.30),
        ])
        filtered = frame.filter_by_confidence(0.50)
        assert len(filtered.detections) == 1

    def test_to_api_dict(self):
        frame  = self._frame([self._det(RetailClass.PERSON)])
        result = frame.to_api_dict()
        assert result["camera_id"]   == "cam-1"
        assert result["person_count"] == 1
        assert "detections"          in result
        assert "inference_ms"        in result


# ── Class Registry ────────────────────────────────────────────────────────────

class TestClassRegistry:
    def test_person_is_coco_class_0(self):
        assert COCO_TO_RETAIL[0] == RetailClass.PERSON

    def test_all_classes_have_meta(self):
        for rc in RetailClass:
            assert rc.value in CLASS_META, f"Missing meta for {rc.name}"

    def test_class_meta_fields(self):
        for rc, meta in CLASS_META.items():
            assert "name"        in meta
            assert "color_hex"   in meta
            assert "min_conf"    in meta
            assert meta["color_hex"].startswith("#")
            assert 0 < meta["min_conf"] < 1

    def test_retail_class_values_distinct(self):
        values = [rc.value for rc in RetailClass]
        assert len(values) == len(set(values))


# ── DetectionConfig ───────────────────────────────────────────────────────────

class TestDetectionConfig:
    def test_defaults(self):
        cfg = DetectionConfig()
        assert cfg.model_path        == "yolo11n.pt"
        assert cfg.confidence_threshold == 0.40
        assert cfg.batch_size        == 4
        assert cfg.device            == "auto"

    def test_explicit_device_returned(self):
        cfg = DetectionConfig(device="cpu")
        assert cfg.resolved_device   == "cpu"

    def test_target_classes_default_includes_person(self):
        cfg = DetectionConfig()
        assert RetailClass.PERSON in cfg.target_classes

    def test_custom_enabled_classes(self):
        cfg = DetectionConfig(enabled_classes=[RetailClass.SHOPPING_CART])
        assert cfg.target_classes == [RetailClass.SHOPPING_CART]

    def test_iou_threshold_bounds(self):
        with pytest.raises(Exception):
            DetectionConfig(iou_threshold=1.5)
        with pytest.raises(Exception):
            DetectionConfig(iou_threshold=0.0)
