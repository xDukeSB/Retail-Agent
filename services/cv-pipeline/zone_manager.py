"""
Zone manager — detects when tracked persons cross named zone boundaries.
Zones are defined as polygons or crossing lines drawn in the UI.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("cv-pipeline.zones")


@dataclass
class Zone:
    name: str
    zone_type: str  # entry | exit | checkout | queue | general
    shape: str  # polygon | line
    points: List[Tuple[float, float]]  # normalized 0-1 coordinates
    color: str = "#3b82f6"


@dataclass
class ZoneCrossing:
    zone_name: str
    zone_type: str
    event_type: str  # entry | exit
    x: float
    y: float
    timestamp: float


class ZoneManager:
    """
    Manages zone polygon/line definitions and detects crossings.
    All coordinates are normalized 0-1.
    """

    def __init__(self, zone_config_json: Optional[str] = None, throttle_seconds: float = 2.0):
        self.zones: List[Zone] = []
        self.throttle_seconds = throttle_seconds
        # Track which zones each person is currently in: {track_id: {zone_name: entry_time}}
        self._person_zone_state: Dict[int, Dict[str, float]] = {}
        # Throttle: last event time per (track_id, zone_name, event_type)
        self._last_event: Dict[str, float] = {}

        if zone_config_json:
            self.load_config(zone_config_json)

    def load_config(self, config_json: str):
        """Load zone definitions from JSON (from camera config)."""
        try:
            data = json.loads(config_json)
            self.zones = []
            for z in data.get("zones", []):
                points = [(p["x"], p["y"]) for p in z.get("points", [])]
                if len(points) >= 2:
                    self.zones.append(Zone(
                        name=z["name"],
                        zone_type=z.get("zone_type", "general"),
                        shape=z.get("type", "polygon"),
                        points=points,
                        color=z.get("color", "#3b82f6"),
                    ))
            logger.info(f"Loaded {len(self.zones)} zones")
        except Exception as e:
            logger.error(f"Failed to load zone config: {e}")

    def _point_in_polygon(self, px: float, py: float, polygon: List[Tuple[float, float]]) -> bool:
        """Ray-casting algorithm for point-in-polygon test."""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi):
                inside = not inside
            j = i
        return inside

    def _crossed_line(
        self,
        prev: Tuple[float, float],
        curr: Tuple[float, float],
        line: List[Tuple[float, float]],
    ) -> bool:
        """Check if movement from prev to curr crosses a line segment."""
        if len(line) < 2:
            return False
        p1, p2 = line[0], line[1]
        # Segment intersection check
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        d1 = cross(p1, p2, prev)
        d2 = cross(p1, p2, curr)
        d3 = cross(prev, curr, p1)
        d4 = cross(prev, curr, p2)
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True
        return False

    def update(
        self,
        track_id: int,
        x: float,
        y: float,
        prev_x: Optional[float],
        prev_y: Optional[float],
        timestamp: float,
    ) -> List[ZoneCrossing]:
        """Check for zone crossings for a tracked person. Returns new crossing events."""
        events = []
        if track_id not in self._person_zone_state:
            self._person_zone_state[track_id] = {}

        for zone in self.zones:
            in_zone = False
            if zone.shape == "polygon" and len(zone.points) >= 3:
                in_zone = self._point_in_polygon(x, y, zone.points)
            elif zone.shape == "line" and prev_x is not None and prev_y is not None:
                in_zone = self._crossed_line((prev_x, prev_y), (x, y), zone.points)

            was_in_zone = zone.name in self._person_zone_state[track_id]

            if in_zone and not was_in_zone:
                # Zone entry
                throttle_key = f"{track_id}:{zone.name}:entry"
                last = self._last_event.get(throttle_key, 0)
                if timestamp - last >= self.throttle_seconds:
                    self._person_zone_state[track_id][zone.name] = timestamp
                    self._last_event[throttle_key] = timestamp
                    events.append(ZoneCrossing(
                        zone_name=zone.name,
                        zone_type=zone.zone_type,
                        event_type="entry",
                        x=x, y=y,
                        timestamp=timestamp,
                    ))

            elif not in_zone and was_in_zone and zone.shape == "polygon":
                # Zone exit
                throttle_key = f"{track_id}:{zone.name}:exit"
                last = self._last_event.get(throttle_key, 0)
                if timestamp - last >= self.throttle_seconds:
                    del self._person_zone_state[track_id][zone.name]
                    self._last_event[throttle_key] = timestamp
                    events.append(ZoneCrossing(
                        zone_name=zone.name,
                        zone_type=zone.zone_type,
                        event_type="exit",
                        x=x, y=y,
                        timestamp=timestamp,
                    ))

        return events

    def get_zones_for_person(self, track_id: int) -> List[str]:
        return list(self._person_zone_state.get(track_id, {}).keys())

    def cleanup_track(self, track_id: int):
        self._person_zone_state.pop(track_id, None)
