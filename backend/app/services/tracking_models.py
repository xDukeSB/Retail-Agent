"""
tracking_models.py — Data models for the ByteTrack visitor tracking pipeline.

Privacy rules enforced here:
  - Visitor IDs are anonymous sequential integers (Visitor #101, #102...)
  - No biometric data, no face crops, no appearance features stored
  - Track IDs are session-ephemeral — reset on service restart
  - Only position centroid and bounding box stored per frame
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, computed_field


# ── Track lifecycle states ─────────────────────────────────────────────────────

class TrackState(str, Enum):
    """
    ByteTrack track lifecycle:

      NEW         → First frame (tentative — may be noise)
      TRACKED     → Actively matched in recent frames
      LOST        → Unmatched for 1..max_lost frames (Kalman predicting)
      REMOVED     → Lost for > max_lost frames → deleted from registry
    """
    NEW      = "new"
    TRACKED  = "tracked"
    LOST     = "lost"
    REMOVED  = "removed"


class VisitorEventType(str, Enum):
    ENTER  = "enter"    # New visitor first confirmed
    EXIT   = "exit"     # Visitor track removed
    DWELL  = "dwell"    # Visitor in dwell zone
    REACQUIRED = "reacquired"   # Lost → Tracked again


# ── Anonymous Visitor ID ───────────────────────────────────────────────────────

class VisitorIDGenerator:
    """
    Generates sequential anonymous visitor IDs starting at 101.

    IDs are session-local — never persisted, never linked across sessions.
    Resets when the tracking service restarts (new deployment session).
    """
    _START = 101

    def __init__(self):
        self._counter = self._START - 1

    def next_id(self) -> int:
        self._counter += 1
        return self._counter

    @staticmethod
    def format(visitor_id: int) -> str:
        return f"Visitor #{visitor_id}"

    def reset(self) -> None:
        self._counter = self._START - 1

    @property
    def total_issued(self) -> int:
        return self._counter - self._START + 1


# ── Position ───────────────────────────────────────────────────────────────────

class Position(BaseModel):
    """Visitor position in absolute pixel coordinates."""
    x:      float   = Field(description="X coordinate of foot-center (pixels)")
    y:      float   = Field(description="Y coordinate of foot-center (pixels)")
    x_norm: float   = Field(ge=0.0, le=1.0, description="Normalized X [0,1]")
    y_norm: float   = Field(ge=0.0, le=1.0, description="Normalized Y [0,1]")

    model_config = {"frozen": True}

    @classmethod
    def from_bbox(
        cls,
        x1: float, y1: float, x2: float, y2: float,
        frame_w: int, frame_h: int,
    ) -> "Position":
        """Use bottom-center as foot position (better for person tracking)."""
        foot_x = (x1 + x2) / 2
        foot_y = y2
        return cls(
            x=foot_x,
            y=foot_y,
            x_norm=min(max(foot_x / frame_w, 0.0), 1.0),
            y_norm=min(max(foot_y / frame_h, 0.0), 1.0),
        )

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "x_norm": self.x_norm, "y_norm": self.y_norm}


# ── Tracked Visitor ────────────────────────────────────────────────────────────

class TrackedVisitor(BaseModel):
    """
    A single tracked visitor in one frame.
    The canonical output unit from the tracking service.
    """
    # Identity (anonymous)
    visitor_id:    int    = Field(description="Sequential anonymous ID (e.g. 101)")
    visitor_label: str    = Field(description="e.g. 'Visitor #101'")
    track_id:      int    = Field(description="Internal ByteTrack track ID (ephemeral)")

    # State
    state:         TrackState
    confidence:    float  = Field(ge=0.0, le=1.0, description="Detection confidence")
    age:           int    = Field(description="Frames since track was created")
    time_since_update: int = Field(default=0, description="Frames since last matched detection")

    # Position
    position:      Position
    bbox:          list[float] = Field(description="[x1, y1, x2, y2] pixel coords")

    # Context
    timestamp:     float
    camera_id:     str
    zone_ids:      list[str]   = Field(default_factory=list)
    class_id:      int         = Field(default=0, description="RetailClass (0=person)")

    model_config = {"frozen": True}

    @computed_field
    @property
    def datetime_utc(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @computed_field
    @property
    def is_confirmed(self) -> bool:
        """Track is confirmed after being active for min_hits frames."""
        return self.state == TrackState.TRACKED and self.age >= 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "visitor_id":    self.visitor_id,
            "visitor_label": self.visitor_label,
            "track_id":      self.track_id,
            "state":         self.state.value,
            "confidence":    round(self.confidence, 4),
            "position":      self.position.to_dict(),
            "bbox":          [round(v, 1) for v in self.bbox],
            "timestamp":     self.timestamp,
            "camera_id":     self.camera_id,
            "age":           self.age,
            "zone_ids":      self.zone_ids,
        }


# ── Tracking Frame ─────────────────────────────────────────────────────────────

class TrackingFrame(BaseModel):
    """All tracked visitors in a single frame from one camera."""
    camera_id:       str
    timestamp:       float
    frame_idx:       int
    frame_shape:     tuple[int, int]   # (H, W)
    tracked:         list[TrackedVisitor]
    lost_count:      int   = Field(default=0, description="Tracks in LOST state")
    total_active:    int   = Field(default=0, description="TRACKED + LOST")
    processing_ms:   float = Field(default=0.0)

    model_config = {"frozen": True}

    @computed_field
    @property
    def visible_count(self) -> int:
        return sum(1 for t in self.tracked if t.state == TrackState.TRACKED)

    @computed_field
    @property
    def confirmed_count(self) -> int:
        return sum(1 for t in self.tracked if t.is_confirmed)

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "camera_id":     self.camera_id,
            "timestamp":     self.timestamp,
            "frame_idx":     self.frame_idx,
            "visitors":      [t.to_dict() for t in self.tracked],
            "visible_count": self.visible_count,
            "confirmed_count": self.confirmed_count,
            "lost_count":    self.lost_count,
            "processing_ms": round(self.processing_ms, 2),
        }


# ── Visitor Events ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VisitorEvent:
    """Lifecycle event emitted when a visitor enters, exits, or dwells."""
    event_type:    VisitorEventType
    visitor_id:    int
    visitor_label: str
    track_id:      int
    camera_id:     str
    timestamp:     float
    position:      Position | None        = None
    dwell_seconds: float                  = 0.0
    zone_ids:      tuple[str, ...]        = ()
    meta:          dict[str, Any]         = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event":         self.event_type.value,
            "visitor_id":    self.visitor_id,
            "visitor_label": self.visitor_label,
            "track_id":      self.track_id,
            "camera_id":     self.camera_id,
            "timestamp":     self.timestamp,
            "position":      self.position.to_dict() if self.position else None,
            "dwell_seconds": round(self.dwell_seconds, 1),
            "zone_ids":      list(self.zone_ids),
        }


# ── Kalman bbox state (raw ndarray wrapper) ────────────────────────────────────

@dataclass
class KalmanBBoxState:
    """
    Wraps the Kalman filter 8-dim state for a bounding box track.
    State vector: [cx, cy, w, h, vx, vy, vw, vh]
    """
    mean:       np.ndarray   # shape (8,)
    covariance: np.ndarray   # shape (8, 8)

    def to_tlwh(self) -> np.ndarray:
        """Convert mean to [top-left-x, top-left-y, width, height]."""
        ret = self.mean[:4].copy()
        ret[0] -= ret[2] / 2   # cx - w/2
        ret[1] -= ret[3] / 2   # cy - h/2
        return ret

    def to_xyxy(self) -> tuple[float, float, float, float]:
        tlwh = self.to_tlwh()
        return float(tlwh[0]), float(tlwh[1]), float(tlwh[0] + tlwh[2]), float(tlwh[1] + tlwh[3])


# ── Track record (internal to ByteTracker) ─────────────────────────────────────

@dataclass
class STrack:
    """
    Single track maintained by ByteTracker.
    Mutable — updated in-place each frame.
    """
    track_id:    int
    visitor_id:  int
    state:       TrackState
    kalman:      KalmanBBoxState
    confidence:  float
    age:         int                      = 1
    hits:        int                      = 1
    time_since_update: int               = 0
    start_ts:    float                   = 0.0
    last_ts:     float                   = 0.0
    class_id:    int                     = 0

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return self.kalman.to_xyxy()

    @property
    def tlwh(self) -> np.ndarray:
        return self.kalman.to_tlwh()

    def mark_tracked(self, confidence: float, ts: float) -> None:
        """Used for TRACKED/LOST tracks matched in current frame."""
        self.state       = TrackState.TRACKED
        self.confidence  = confidence
        self.last_ts     = ts
        self.hits       += 1
        self.time_since_update = 0

    def mark_hit(self, confidence: float, ts: float) -> None:
        """Used for NEW tracks — accumulates hits without promoting state to TRACKED.
        The ByteTracker promotion loop handles NEW → TRACKED after min_hits."""
        self.confidence  = confidence
        self.last_ts     = ts
        self.hits       += 1
        self.time_since_update = 0

    def mark_lost(self) -> None:
        self.state            = TrackState.LOST
        self.time_since_update += 1

    def mark_removed(self) -> None:
        self.state = TrackState.REMOVED
