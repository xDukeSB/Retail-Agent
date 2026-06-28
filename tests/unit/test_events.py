"""
test_events.py — Unit tests for line crossing and event engine.

Tests:
  VirtualLine — side_of, crossing_direction, validation, from_dict/to_dict
  VisitorLineState — single flip, hysteresis (min_crossings), same side
  LineCrossingDetector — add/remove lines, process_frame, purge_visitor
  CrossingEventType resolution — ENTRY line, EXIT line, BOTH line
  EventMetrics — counter increments
"""
from __future__ import annotations

import math
import sys
import types
from unittest.mock import MagicMock, AsyncMock
from typing import Optional

import pytest

# Mock heavy deps
for mod in ["torch", "ultralytics", "cv2"]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

from app.services.line_crossing import (
    CrossingDirection, CrossingEventType, LineCrossing,
    LineCrossingDetector, LineType, VirtualLine, VisitorLineState,
    line_crossing_detector,
)
from app.services.tracking_models import Position, TrackedVisitor, TrackState


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_line(
    x1=0.0, y1=0.5, x2=1.0, y2=0.5,
    line_type="entry",
    flip=False,
    min_crossings=1,
    camera_id="cam-1",
    line_id="line-001",
) -> VirtualLine:
    """Horizontal line at y=0.5, spanning full width."""
    return VirtualLine(
        id=line_id,
        camera_id=camera_id,
        name="Test Line",
        line_type=LineType(line_type),
        x1=x1, y1=y1, x2=x2, y2=y2,
        flip_direction=flip,
        min_crossings=min_crossings,
    )


def make_visitor(
    visitor_id=101,
    x_norm=0.5,
    y_norm=0.3,
    camera_id="cam-1",
    state=TrackState.TRACKED,
    confidence=0.9,
) -> TrackedVisitor:
    return TrackedVisitor(
        visitor_id=visitor_id,
        visitor_label=f"Visitor #{visitor_id}",
        track_id=visitor_id,
        state=state,
        confidence=confidence,
        age=5,
        position=Position(x=x_norm * 640, y=y_norm * 480, x_norm=x_norm, y_norm=y_norm),
        bbox=[0, 0, 100, 200],
        timestamp=1_700_000_000.0,
        camera_id=camera_id,
    )


# ── VirtualLine ───────────────────────────────────────────────────────────────

class TestVirtualLine:
    def _hline(self, flip=False) -> VirtualLine:
        """Horizontal line at y=0.5 from x=0 to x=1."""
        return make_line(flip=flip)

    def test_side_of_above_is_negative(self):
        line = self._hline()
        # Cross product of left→right line AB × AP where P is above line (y < 0.5)
        # = (1-0)*(0.2-0.5) - (0.5-0.5)*(0.5-0.0) = -0.3  → negative
        assert line.side_of(0.5, 0.2) < 0

    def test_side_of_below_is_positive(self):
        line = self._hline()
        # P below line (y > 0.5) → positive cross product
        assert line.side_of(0.5, 0.8) > 0

    def test_side_of_on_line_is_zero(self):
        line = self._hline()
        assert abs(line.side_of(0.5, 0.5)) < 1e-9

    def test_flip_inverts_sign(self):
        line_normal = self._hline(flip=False)
        line_flip   = self._hline(flip=True)
        # Same point should give opposite signs
        assert line_normal.side_of(0.5, 0.2) == -line_flip.side_of(0.5, 0.2)

    def test_crossing_direction_positive_to_negative_is_out(self):
        line = self._hline()
        direction = line.crossing_direction(+1.0, -1.0)
        assert direction == CrossingDirection.OUT

    def test_crossing_direction_negative_to_positive_is_in(self):
        line = self._hline()
        direction = line.crossing_direction(-1.0, +1.0)
        assert direction == CrossingDirection.IN

    def test_crossing_direction_same_sign_is_none(self):
        line = self._hline()
        assert line.crossing_direction(+1.0, +2.0) is None
        assert line.crossing_direction(-1.0, -2.0) is None

    def test_crossing_direction_zero_is_none(self):
        line = self._hline()
        assert line.crossing_direction(0.0, +1.0) is None
        assert line.crossing_direction(+1.0, 0.0) is None

    def test_line_length(self):
        line = self._hline()
        assert abs(line.length - 1.0) < 1e-9

    def test_invalid_coord_raises(self):
        with pytest.raises(ValueError):
            VirtualLine(
                id="l1", camera_id="c1", name="Bad",
                line_type=LineType.ENTRY,
                x1=1.5, y1=0.5, x2=0.5, y2=0.5,   # x1 > 1.0
            )

    def test_zero_length_raises(self):
        with pytest.raises(ValueError):
            VirtualLine(
                id="l1", camera_id="c1", name="Bad",
                line_type=LineType.ENTRY,
                x1=0.5, y1=0.5, x2=0.5, y2=0.5,   # identical points
            )

    def test_to_dict_from_dict_roundtrip(self):
        line   = make_line()
        d      = line.to_dict()
        line2  = VirtualLine.from_dict(d)
        assert line2.id        == line.id
        assert line2.camera_id == line.camera_id
        assert abs(line2.x1    - line.x1) < 1e-9
        assert line2.line_type == line.line_type


# ── VisitorLineState ──────────────────────────────────────────────────────────

class TestVisitorLineState:
    def test_first_update_returns_none(self):
        state = VisitorLineState(visitor_id=101, line_id="l1")
        result = state.update(+1.0, min_crossings=1)
        assert result is None

    def test_sign_flip_confirms_crossing(self):
        state  = VisitorLineState(visitor_id=101, line_id="l1")
        state.update(+1.0, min_crossings=1)   # set initial side
        result = state.update(-1.0, min_crossings=1)
        assert result == CrossingDirection.OUT

    def test_same_side_returns_none(self):
        state  = VisitorLineState(visitor_id=101, line_id="l1")
        state.update(+1.0, min_crossings=1)
        result = state.update(+2.0, min_crossings=1)
        assert result is None

    def test_hysteresis_requires_multiple_flips(self):
        state  = VisitorLineState(visitor_id=101, line_id="l1")
        state.update(+1.0, min_crossings=3)   # establish initial side

        # Call update with negative side 3 times consecutively
        result1 = state.update(-1.0, min_crossings=3)   # flip 1 — pending=1
        assert result1 is None

        result2 = state.update(-1.0, min_crossings=3)   # flip 2 — pending=2
        assert result2 is None

        result3 = state.update(-1.0, min_crossings=3)   # flip 3 — confirmed!
        assert result3 == CrossingDirection.OUT

    def test_direction_change_resets_counter(self):
        state  = VisitorLineState(visitor_id=101, line_id="l1")
        state.update(+1.0, min_crossings=3)
        state.update(-1.0, min_crossings=3)   # flip 1 toward OUT
        result = state.update(+1.0, min_crossings=3)  # flip back → reset
        assert result is None
        assert state.pending_count == 0 or state.pending_dir != CrossingDirection.OUT

    def test_in_direction_detected(self):
        state  = VisitorLineState(visitor_id=101, line_id="l1")
        state.update(-1.0, min_crossings=1)   # start on negative side
        result = state.update(+1.0, min_crossings=1)
        assert result == CrossingDirection.IN


# ── LineCrossingDetector ──────────────────────────────────────────────────────

class TestLineCrossingDetector:
    def _detector(self) -> LineCrossingDetector:
        return LineCrossingDetector()

    def test_add_line_registers(self):
        det  = self._detector()
        line = make_line()
        det.add_line(line)
        assert len(det.get_lines("cam-1")) == 1

    def test_remove_line_works(self):
        det  = self._detector()
        line = make_line()
        det.add_line(line)
        removed = det.remove_line("cam-1", "line-001")
        assert removed is True
        assert len(det.get_lines("cam-1")) == 0

    def test_remove_nonexistent_returns_false(self):
        det  = self._detector()
        removed = det.remove_line("cam-1", "ghost")
        assert removed is False

    def test_no_lines_returns_empty(self):
        det      = self._detector()
        visitor  = make_visitor(y_norm=0.3)
        crossings = det.process_frame("cam-1", [visitor], 1000.0)
        assert crossings == []

    def test_no_visitors_returns_empty(self):
        det  = self._detector()
        det.add_line(make_line())
        crossings = det.process_frame("cam-1", [], 1000.0)
        assert crossings == []

    def test_crossing_detected_on_sign_flip(self):
        det  = self._detector()
        det.add_line(make_line())    # horizontal line at y=0.5

        # Frame 1: visitor above line (y=0.3)
        # For left→right horizontal line, above (y<0.5) is NEGATIVE side
        v1 = make_visitor(y_norm=0.3)
        det.process_frame("cam-1", [v1], 1000.0)

        # Frame 2: visitor below line (y=0.7) → POSITIVE side
        # Sign changed: negative → positive = CrossingDirection.IN
        v2 = make_visitor(y_norm=0.7)
        crossings = det.process_frame("cam-1", [v2], 1001.0)
        assert len(crossings) == 1
        assert crossings[0].direction in (CrossingDirection.IN, CrossingDirection.OUT)
        # EventType should be CUSTOMER_ENTERED (line_type=entry, direction=IN)
        assert crossings[0].event_type == CrossingEventType.CUSTOMER_ENTERED

    def test_no_crossing_same_side(self):
        det = self._detector()
        det.add_line(make_line())
        v1 = make_visitor(y_norm=0.3)
        det.process_frame("cam-1", [v1], 1000.0)
        v2 = make_visitor(y_norm=0.4)   # still above line
        crossings = det.process_frame("cam-1", [v2], 1001.0)
        assert crossings == []

    def test_crossing_contains_visitor_info(self):
        det = self._detector()
        det.add_line(make_line())
        det.process_frame("cam-1", [make_visitor(y_norm=0.3)], 1000.0)
        crossings = det.process_frame("cam-1", [make_visitor(y_norm=0.7)], 1001.0)
        assert crossings[0].visitor_id == 101
        assert crossings[0].visitor_label == "Visitor #101"
        assert crossings[0].camera_id == "cam-1"

    def test_multiple_visitors_tracked_independently(self):
        det  = self._detector()
        det.add_line(make_line())

        # Both above first
        det.process_frame("cam-1", [
            make_visitor(visitor_id=101, y_norm=0.3),
            make_visitor(visitor_id=102, y_norm=0.3),
        ], 1000.0)

        # Only visitor 101 crosses
        crossings = det.process_frame("cam-1", [
            make_visitor(visitor_id=101, y_norm=0.7),   # crossed!
            make_visitor(visitor_id=102, y_norm=0.4),   # still above
        ], 1001.0)
        assert len(crossings) == 1
        assert crossings[0].visitor_id == 101

    def test_purge_visitor_cleans_state(self):
        det  = self._detector()
        det.add_line(make_line())
        det.process_frame("cam-1", [make_visitor(y_norm=0.3)], 1000.0)
        det.purge_visitor("cam-1", 101)
        # After purge, state is fresh — crossing detection resets
        crossings = det.process_frame("cam-1", [make_visitor(y_norm=0.7)], 1001.0)
        # First observation after purge — no crossing (new initial state)
        assert crossings == []

    def test_status_output(self):
        det  = self._detector()
        det.add_line(make_line())
        status = det.get_status()
        assert status["total_lines"] == 1
        assert status["cameras"] == 1


# ── CrossingEventType resolution ─────────────────────────────────────────────

class TestCrossingEventTypeResolution:
    def _resolve(self, line_type, direction) -> CrossingEventType:
        return LineCrossingDetector._resolve_event_type(
            VirtualLine(
                id="x", camera_id="c", name="n",
                line_type=LineType(line_type),
                x1=0.0, y1=0.0, x2=1.0, y2=0.5,
            ),
            CrossingDirection(direction),
        )

    def test_entry_line_in_direction_is_entered(self):
        assert self._resolve("entry", "in") == CrossingEventType.CUSTOMER_ENTERED

    def test_entry_line_out_direction_is_exited(self):
        assert self._resolve("entry", "out") == CrossingEventType.CUSTOMER_EXITED

    def test_exit_line_out_direction_is_exited(self):
        assert self._resolve("exit", "out") == CrossingEventType.CUSTOMER_EXITED

    def test_exit_line_in_direction_is_entered(self):
        assert self._resolve("exit", "in") == CrossingEventType.CUSTOMER_ENTERED

    def test_both_line_in_is_entered(self):
        assert self._resolve("both", "in") == CrossingEventType.CUSTOMER_ENTERED

    def test_both_line_out_is_exited(self):
        assert self._resolve("both", "out") == CrossingEventType.CUSTOMER_EXITED


# ── LineCrossing.to_dict ──────────────────────────────────────────────────────

class TestLineCrossing:
    def test_to_dict_has_required_fields(self):
        from app.services.line_crossing import LineCrossing, LineType, CrossingDirection, CrossingEventType
        crossing = LineCrossing(
            line_id="l1",
            line_name="Entrance",
            line_type=LineType.ENTRY,
            camera_id="cam-1",
            visitor_id=101,
            visitor_label="Visitor #101",
            track_id=1,
            direction=CrossingDirection.IN,
            event_type=CrossingEventType.CUSTOMER_ENTERED,
            timestamp=1_700_000_000.0,
            confidence=0.85,
            position_x=0.5,
            position_y=0.5,
        )
        d = crossing.to_dict()
        assert d["event_type"] == "customer_entered"
        assert d["visitor_id"] == 101
        assert d["direction"]  == "in"
        assert "position"      in d
        assert d["confidence"] == 0.85
