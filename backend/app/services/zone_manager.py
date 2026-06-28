"""
zone_manager.py — Retail zone configuration and point-in-zone testing.

Zones are named polygonal regions drawn on a camera's field of view.
Each camera can have multiple zones of different types:

  ENTRANCE      — door area for in/out counting
  EXIT          — exit door area
  CHECKOUT      — checkout counter queue zone
  DWELL         — product aisle / display area
  RESTRICTED    — staff-only area (triggers alert if customer detected)

Zone geometry is stored as normalized polygon vertices [0, 1].
Point-in-polygon uses the ray-casting algorithm (O(n) per vertex).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.logging import get_logger
from app.services.detection_models import BoundingBox

logger = get_logger(__name__)


class ZoneType(str, Enum):
    ENTRANCE   = "entrance"
    EXIT       = "exit"
    CHECKOUT   = "checkout"
    DWELL      = "dwell"
    RESTRICTED = "restricted"
    DRINKS     = "drinks"
    SNACKS     = "snacks"
    ELECTRONICS = "electronics"
    COSMETICS  = "cosmetics"
    CUSTOM     = "custom"


@dataclass
class Zone:
    """
    Polygonal zone in normalized [0, 1] coordinates.
    vertices = [(x1, y1), (x2, y2), ...]  — clockwise or counter-clockwise.
    """
    id:         str
    name:       str
    type:       ZoneType
    camera_id:  str
    vertices:   list[tuple[float, float]]   # normalized coords
    is_active:  bool = True
    meta:       dict = field(default_factory=dict)

    def contains_point(self, x_norm: float, y_norm: float) -> bool:
        """Ray-casting point-in-polygon test. O(n) in number of vertices."""
        n       = len(self.vertices)
        inside  = False
        px, py  = x_norm, y_norm
        j       = n - 1
        for i in range(n):
            xi, yi = self.vertices[i]
            xj, yj = self.vertices[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
        return inside

    def contains_bbox_centroid(self, bbox: BoundingBox, frame_w: int, frame_h: int) -> bool:
        """Check if a bounding box centroid falls inside this zone."""
        cx_norm = bbox.center_x / frame_w
        cy_norm = bbox.center_y / frame_h
        return self.contains_point(cx_norm, cy_norm)

    def contains_bbox_bottom_center(self, bbox: BoundingBox, frame_w: int, frame_h: int) -> bool:
        """Check using bottom-center of bbox (foot position for person detection)."""
        bx_norm = bbox.center_x / frame_w
        by_norm = bbox.y2 / frame_h
        return self.contains_point(bx_norm, by_norm)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":        self.id,
            "name":      self.name,
            "type":      self.type.value,
            "camera_id": self.camera_id,
            "vertices":  [[v[0], v[1]] for v in self.vertices],
            "is_active": self.is_active,
            "meta":      self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Zone":
        return cls(
            id=data["id"],
            name=data["name"],
            type=ZoneType(data.get("type", "custom")),
            camera_id=data["camera_id"],
            vertices=[(v[0], v[1]) for v in data["vertices"]],
            is_active=data.get("is_active", True),
            meta=data.get("meta", {}),
        )


class ZoneManager:
    """
    In-memory zone registry. Zones are loaded from the camera's
    `zone_config` JSON blob (stored in the Camera model).

    Thread-safe for async read access.
    """

    def __init__(self):
        self._zones: dict[str, list[Zone]] = {}   # camera_id → zones

    def load_from_camera(self, camera_id: str, zone_config_json: str | None) -> int:
        """Parse zone_config JSON and load zones for a camera."""
        if not zone_config_json:
            self._zones[camera_id] = []
            return 0
        try:
            config = json.loads(zone_config_json)
            zones  = [Zone.from_dict(z) for z in config.get("zones", [])]
            self._zones[camera_id] = zones
            logger.info("Zones loaded", extra={"camera_id": camera_id, "count": len(zones)})
            return len(zones)
        except Exception as exc:
            logger.error("Zone config parse error", extra={"camera_id": camera_id, "error": str(exc)})
            self._zones[camera_id] = []
            return 0

    def get_zones(self, camera_id: str) -> list[Zone]:
        return self._zones.get(camera_id, [])

    def get_active_zones(self, camera_id: str) -> list[Zone]:
        return [z for z in self.get_zones(camera_id) if z.is_active]

    def add_zone(self, zone: Zone) -> None:
        if zone.camera_id not in self._zones:
            self._zones[zone.camera_id] = []
        self._zones[zone.camera_id].append(zone)

    def remove_zone(self, camera_id: str, zone_id: str) -> bool:
        zones = self._zones.get(camera_id, [])
        before = len(zones)
        self._zones[camera_id] = [z for z in zones if z.id != zone_id]
        return len(self._zones[camera_id]) < before

    def get_zones_for_point(
        self, camera_id: str, x_norm: float, y_norm: float
    ) -> list[Zone]:
        """Return all active zones that contain the given point."""
        return [
            z for z in self.get_active_zones(camera_id)
            if z.contains_point(x_norm, y_norm)
        ]

    def annotate_detection(
        self,
        camera_id: str,
        bbox: BoundingBox,
        frame_w: int,
        frame_h: int,
        use_foot: bool = True,
    ) -> list[str]:
        """Return zone IDs that a detection falls within."""
        zones = self.get_active_zones(camera_id)
        matched: list[str] = []
        for zone in zones:
            if use_foot:
                hit = zone.contains_bbox_bottom_center(bbox, frame_w, frame_h)
            else:
                hit = zone.contains_bbox_centroid(bbox, frame_w, frame_h)
            if hit:
                matched.append(zone.id)
        return matched

    def export_camera_config(self, camera_id: str) -> str:
        """Serialize all zones for a camera to JSON (for DB storage)."""
        zones = self.get_zones(camera_id)
        return json.dumps({"zones": [z.to_dict() for z in zones]})

    def get_status(self) -> dict:
        return {
            "cameras": len(self._zones),
            "total_zones": sum(len(v) for v in self._zones.values()),
            "by_camera": {
                cid: len(zones) for cid, zones in self._zones.items()
            },
        }


zone_manager = ZoneManager()
