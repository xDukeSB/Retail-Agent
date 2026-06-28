"""
line_crossing.py — Virtual line crossing detection for entry/exit counting.

Core algorithm:
  Given a line segment AB defined by two normalized points, we test which
  "side" of the line a tracked visitor's foot position is on using the
  2D cross-product (signed area) of vector AB × AP.

  Crossing is detected when the sign flips between consecutive frames.
  Direction of crossing determines ENTRY vs EXIT.

Line orientation convention:
  Each line has an INSIDE direction (the store side) and an OUTSIDE
  direction (the street side).  When a visitor moves from OUTSIDE → INSIDE,
  that is an ENTRY.  The reverse is an EXIT.

  The store owner draws the line and picks which side is "inside" via a
  flag (flip_direction=False by default means:
    positive cross-product side = INSIDE).

Coordinates:
  All coordinates are NORMALIZED [0, 1] relative to frame size.
  This makes lines resolution-independent.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Line type ──────────────────────────────────────────────────────────────────

class LineType(str, Enum):
    ENTRY  = "entry"    # This line marks the entrance
    EXIT   = "exit"     # This line marks the exit
    BOTH   = "both"     # Bidirectional line (crossing in either direction is recorded)


class CrossingDirection(str, Enum):
    IN   = "in"    # Visitor moved from outside → inside (ENTRY)
    OUT  = "out"   # Visitor moved from inside → outside (EXIT)


class CrossingEventType(str, Enum):
    CUSTOMER_ENTERED = "customer_entered"
    CUSTOMER_EXITED  = "customer_exited"
    UNKNOWN          = "unknown"   # BOTH-type line, direction unclear


# ── Virtual Line ───────────────────────────────────────────────────────────────

@dataclass
class VirtualLine:
    """
    A line segment defined in normalized [0,1] frame coordinates.
    Drawn by the store owner via the UI.

    Fields:
      id            — Unique line ID (UUID)
      camera_id     — Which camera this line belongs to
      name          — Human label (e.g. "Main Entrance", "Side Exit")
      line_type     — ENTRY / EXIT / BOTH
      x1, y1        — Start point (normalized)
      x2, y2        — End point (normalized)
      flip_direction — If True, swap inside/outside sides
      is_active     — Whether crossing detection is enabled
      min_crossings — Number of consecutive sign flips to confirm crossing
                      (reduces noise / false positives)
    """
    id:              str
    camera_id:       str
    name:            str
    line_type:       LineType
    x1:              float   # Normalized [0, 1]
    y1:              float
    x2:              float
    y2:              float
    flip_direction:  bool    = False
    is_active:       bool    = True
    min_crossings:   int     = 1    # 1 = single frame flip (faster); 2+ = more stable
    meta:            dict    = field(default_factory=dict)

    def __post_init__(self):
        # Validate normalization
        for val, name in [(self.x1, "x1"), (self.y1, "y1"), (self.x2, "x2"), (self.y2, "y2")]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"VirtualLine.{name}={val} must be in [0, 1]")
        # Ensure line has non-zero length
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if math.hypot(dx, dy) < 1e-6:
            raise ValueError("VirtualLine: start and end points are identical")

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def side_of(self, px: float, py: float) -> float:
        """
        2D cross product of AB × AP.
        Positive → left side of AB (when looking from A to B).
        Negative → right side.
        Zero      → point is on the line.

        If flip_direction is True, the sign is negated so the store owner
        can define "inside" visually without worrying about line draw order.
        """
        cross = (self.x2 - self.x1) * (py - self.y1) - (self.y2 - self.y1) * (px - self.x1)
        return -cross if self.flip_direction else cross

    def crossing_direction(self, side_prev: float, side_curr: float) -> Optional[CrossingDirection]:
        """
        Returns the crossing direction if a sign flip occurred, else None.
        Uses strict sign flip (ignores zero — point exactly on line).
        """
        if side_prev == 0.0 or side_curr == 0.0:
            return None   # on the line — ambiguous
        if side_prev > 0 and side_curr < 0:
            return CrossingDirection.OUT   # left → right = going out
        if side_prev < 0 and side_curr > 0:
            return CrossingDirection.IN    # right → left = going in
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":             self.id,
            "camera_id":      self.camera_id,
            "name":           self.name,
            "line_type":      self.line_type.value,
            "x1": self.x1, "y1": self.y1,
            "x2": self.x2, "y2": self.y2,
            "flip_direction": self.flip_direction,
            "is_active":      self.is_active,
            "min_crossings":  self.min_crossings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VirtualLine":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            camera_id=data["camera_id"],
            name=data.get("name", "Line"),
            line_type=LineType(data.get("line_type", "both")),
            x1=float(data["x1"]), y1=float(data["y1"]),
            x2=float(data["x2"]), y2=float(data["y2"]),
            flip_direction=data.get("flip_direction", False),
            is_active=data.get("is_active", True),
            min_crossings=data.get("min_crossings", 1),
            meta=data.get("meta", {}),
        )


# ── Detected crossing event ────────────────────────────────────────────────────

@dataclass(frozen=True)
class LineCrossing:
    """A confirmed line-crossing event for one visitor on one line."""
    line_id:      str
    line_name:    str
    line_type:    LineType
    camera_id:    str
    visitor_id:   int
    visitor_label: str
    track_id:     int
    direction:    CrossingDirection
    event_type:   CrossingEventType
    timestamp:    float
    confidence:   float
    position_x:  float   # Where they crossed (normalized)
    position_y:  float

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id":       self.line_id,
            "line_name":     self.line_name,
            "line_type":     self.line_type.value,
            "camera_id":     self.camera_id,
            "visitor_id":    self.visitor_id,
            "visitor_label": self.visitor_label,
            "track_id":      self.track_id,
            "direction":     self.direction.value,
            "event_type":    self.event_type.value,
            "timestamp":     self.timestamp,
            "confidence":    round(self.confidence, 4),
            "position":      {"x_norm": self.position_x, "y_norm": self.position_y},
        }


# ── Per-visitor line state ─────────────────────────────────────────────────────

@dataclass
class VisitorLineState:
    """
    Tracks a visitor's relationship with a single line across frames.
    Handles hysteresis via min_crossings confirmation counter.
    """
    visitor_id:   int
    line_id:      str
    last_side:    Optional[float]   = None   # last computed cross product
    pending_dir:  Optional[CrossingDirection] = None
    pending_count: int              = 0      # frames confirming a crossing

    def update(
        self,
        current_side: float,
        min_crossings: int,
    ) -> Optional[CrossingDirection]:
        """
        Update state with new cross-product value.
        Returns a confirmed CrossingDirection on confirmation, else None.
        """
        if current_side == 0.0:
            return None

        if self.last_side is None or self.last_side == 0.0:
            self.last_side = current_side
            return None

        # Detect sign flip
        if (self.last_side > 0) != (current_side > 0):
            # Sign flipped
            tentative = (
                CrossingDirection.OUT if (self.last_side > 0 and current_side < 0)
                else CrossingDirection.IN
            )
            if self.pending_dir == tentative:
                self.pending_count += 1
            else:
                self.pending_dir   = tentative
                self.pending_count = 1

            if self.pending_count >= min_crossings:
                self.last_side    = current_side
                self.pending_dir  = None
                self.pending_count = 0
                return tentative
        else:
            # Same side — reset any pending crossing
            self.pending_dir  = None
            self.pending_count = 0
            self.last_side = current_side

        return None


# ── Line Crossing Detector ─────────────────────────────────────────────────────

class LineCrossingDetector:
    """
    Maintains state for all virtual lines on all cameras.
    Called once per TrackingFrame to detect crossings.

    State: per-camera → per-line → per-visitor → VisitorLineState
    """

    def __init__(self):
        # camera_id → list[VirtualLine]
        self._lines: dict[str, list[VirtualLine]] = {}
        # (camera_id, line_id, visitor_id) → VisitorLineState
        self._states: dict[tuple[str, str, int], VisitorLineState] = {}

    # ── Line registry ──────────────────────────────────────────────────────────

    def add_line(self, line: VirtualLine) -> None:
        if line.camera_id not in self._lines:
            self._lines[line.camera_id] = []
        # Replace existing line with same ID
        self._lines[line.camera_id] = [
            l for l in self._lines[line.camera_id] if l.id != line.id
        ]
        self._lines[line.camera_id].append(line)
        logger.info("Line added", extra={"camera_id": line.camera_id, "line_id": line.id, "name": line.name})

    def remove_line(self, camera_id: str, line_id: str) -> bool:
        lines = self._lines.get(camera_id, [])
        before = len(lines)
        self._lines[camera_id] = [l for l in lines if l.id != line_id]
        # Purge all visitor states for this line
        keys_to_delete = [k for k in self._states if k[0] == camera_id and k[1] == line_id]
        for k in keys_to_delete:
            del self._states[k]
        return len(self._lines[camera_id]) < before

    def get_lines(self, camera_id: str) -> list[VirtualLine]:
        return self._lines.get(camera_id, [])

    def update_line(self, line: VirtualLine) -> None:
        self.add_line(line)   # add_line replaces existing

    def purge_visitor(self, camera_id: str, visitor_id: int) -> None:
        """Remove state for a visitor who has exited (REMOVED state)."""
        keys = [k for k in self._states if k[0] == camera_id and k[2] == visitor_id]
        for k in keys:
            del self._states[k]

    # ── Core processing ────────────────────────────────────────────────────────

    def process_frame(
        self,
        camera_id: str,
        visitors: list,           # list[TrackedVisitor] from tracking_models
        timestamp: float,
    ) -> list[LineCrossing]:
        """
        Process one tracking frame.
        Returns all confirmed crossing events in this frame.
        """
        lines = [l for l in self._lines.get(camera_id, []) if l.is_active]
        if not lines or not visitors:
            return []

        crossings: list[LineCrossing] = []

        for line in lines:
            for visitor in visitors:
                key   = (camera_id, line.id, visitor.visitor_id)
                state = self._states.setdefault(key, VisitorLineState(
                    visitor_id=visitor.visitor_id,
                    line_id=line.id,
                ))

                px = visitor.position.x_norm
                py = visitor.position.y_norm
                side = line.side_of(px, py)

                confirmed_dir = state.update(side, line.min_crossings)
                if confirmed_dir is None:
                    continue

                event_type = self._resolve_event_type(line, confirmed_dir)
                crossing   = LineCrossing(
                    line_id=line.id,
                    line_name=line.name,
                    line_type=line.line_type,
                    camera_id=camera_id,
                    visitor_id=visitor.visitor_id,
                    visitor_label=visitor.visitor_label,
                    track_id=visitor.track_id,
                    direction=confirmed_dir,
                    event_type=event_type,
                    timestamp=timestamp,
                    confidence=visitor.confidence,
                    position_x=px,
                    position_y=py,
                )
                crossings.append(crossing)
                logger.info(
                    "Line crossed",
                    extra={
                        "event":      event_type.value,
                        "visitor":    visitor.visitor_label,
                        "line":       line.name,
                        "camera_id":  camera_id,
                        "direction":  confirmed_dir.value,
                    },
                )

        return crossings

    @staticmethod
    def _resolve_event_type(line: VirtualLine, direction: CrossingDirection) -> CrossingEventType:
        if line.line_type == LineType.ENTRY:
            return CrossingEventType.CUSTOMER_ENTERED if direction == CrossingDirection.IN else CrossingEventType.CUSTOMER_EXITED
        if line.line_type == LineType.EXIT:
            return CrossingEventType.CUSTOMER_EXITED if direction == CrossingDirection.OUT else CrossingEventType.CUSTOMER_ENTERED
        # BOTH — use direction convention directly
        if direction == CrossingDirection.IN:
            return CrossingEventType.CUSTOMER_ENTERED
        return CrossingEventType.CUSTOMER_EXITED

    def get_status(self) -> dict[str, Any]:
        return {
            "cameras":      len(self._lines),
            "total_lines":  sum(len(v) for v in self._lines.values()),
            "total_states": len(self._states),
            "by_camera": {
                cid: len(lines) for cid, lines in self._lines.items()
            },
        }


# Singleton detector
line_crossing_detector = LineCrossingDetector()
