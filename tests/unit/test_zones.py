"""
Unit tests for detection service — zone manager and detection models.
Extends the existing detection test suite.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# Mock heavy deps
for mod in ["torch", "ultralytics", "cv2"]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

import numpy as np

from app.services.zone_manager import Zone, ZoneManager, ZoneType
from app.services.detection_models import BoundingBox


class TestZonePointInPolygon:
    """Test the ray-casting point-in-polygon algorithm."""

    def _square(self) -> Zone:
        return Zone(
            id="z1", name="Test Zone", type=ZoneType.DWELL,
            camera_id="cam-1",
            vertices=[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)],
        )

    def test_center_point_inside(self):
        zone = self._square()
        assert zone.contains_point(0.5, 0.5) is True

    def test_corner_outside(self):
        zone = self._square()
        assert zone.contains_point(0.0, 0.0) is False

    def test_edge_outside(self):
        zone = self._square()
        assert zone.contains_point(0.1, 0.5) is False

    def test_far_outside(self):
        zone = self._square()
        assert zone.contains_point(0.99, 0.99) is False

    def test_triangle_zone(self):
        tri = Zone(
            id="z2", name="Triangle", type=ZoneType.ENTRANCE,
            camera_id="cam-1",
            vertices=[(0.5, 0.0), (1.0, 1.0), (0.0, 1.0)],
        )
        assert tri.contains_point(0.5, 0.8) is True
        assert tri.contains_point(0.01, 0.01) is False

    def test_bbox_centroid(self):
        zone = self._square()
        # bbox centroid at (0.5, 0.5) norm → inside
        bbox = BoundingBox(x1=280, y1=220, x2=360, y2=300)
        assert zone.contains_bbox_centroid(bbox, frame_w=640, frame_h=480) is True

    def test_bbox_outside(self):
        zone = self._square()
        bbox = BoundingBox(x1=0, y1=0, x2=60, y2=60)
        assert zone.contains_bbox_centroid(bbox, frame_w=640, frame_h=480) is False


class TestZoneManager:
    def _manager(self) -> ZoneManager:
        m = ZoneManager()
        m.add_zone(Zone(
            id="entrance", name="Entrance", type=ZoneType.ENTRANCE,
            camera_id="cam-1",
            vertices=[(0.0, 0.0), (0.3, 0.0), (0.3, 1.0), (0.0, 1.0)],
        ))
        m.add_zone(Zone(
            id="checkout", name="Checkout", type=ZoneType.CHECKOUT,
            camera_id="cam-1",
            vertices=[(0.7, 0.0), (1.0, 0.0), (1.0, 1.0), (0.7, 1.0)],
        ))
        return m

    def test_get_zones(self):
        m = self._manager()
        assert len(m.get_zones("cam-1")) == 2

    def test_unknown_camera_returns_empty(self):
        m = self._manager()
        assert m.get_zones("nonexistent") == []

    def test_get_zones_for_point_entrance(self):
        m = self._manager()
        zones = m.get_zones_for_point("cam-1", 0.15, 0.5)
        assert any(z.id == "entrance" for z in zones)
        assert not any(z.id == "checkout" for z in zones)

    def test_get_zones_for_point_checkout(self):
        m = self._manager()
        zones = m.get_zones_for_point("cam-1", 0.85, 0.5)
        assert any(z.id == "checkout" for z in zones)

    def test_get_zones_for_point_middle(self):
        m = self._manager()
        zones = m.get_zones_for_point("cam-1", 0.5, 0.5)
        assert len(zones) == 0   # between entrance and checkout

    def test_remove_zone(self):
        m = self._manager()
        removed = m.remove_zone("cam-1", "entrance")
        assert removed is True
        assert len(m.get_zones("cam-1")) == 1

    def test_remove_nonexistent_zone(self):
        m = self._manager()
        removed = m.remove_zone("cam-1", "ghost")
        assert removed is False

    def test_annotate_detection(self):
        m = self._manager()
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=480)   # leftmost 15% width
        zone_ids = m.annotate_detection("cam-1", bbox, frame_w=640, frame_h=480, use_foot=False)
        assert "entrance" in zone_ids

    def test_export_and_load(self):
        m = self._manager()
        exported = m.export_camera_config("cam-1")
        m2 = ZoneManager()
        count = m2.load_from_camera("cam-1", exported)
        assert count == 2
        assert len(m2.get_zones("cam-1")) == 2

    def test_load_empty_config(self):
        m = ZoneManager()
        count = m.load_from_camera("cam-1", None)
        assert count == 0

    def test_load_invalid_json(self):
        m = ZoneManager()
        count = m.load_from_camera("cam-1", "not json{{{")
        assert count == 0
        assert m.get_zones("cam-1") == []

    def test_inactive_zone_excluded(self):
        m = ZoneManager()
        m.add_zone(Zone(
            id="disabled", name="Disabled", type=ZoneType.DWELL,
            camera_id="cam-1",
            vertices=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
            is_active=False,
        ))
        active = m.get_active_zones("cam-1")
        assert len(active) == 0

    def test_zone_status(self):
        m = self._manager()
        status = m.get_status()
        assert status["total_zones"] == 2
        assert status["cameras"] == 1
