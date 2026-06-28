"""
test_tracking.py — Unit tests for the ByteTrack visitor tracking service.

Tests:
  - VisitorIDGenerator: sequential IDs, format, reset
  - KalmanFilter: initiate, predict, update, gating distance
  - IoU batch: identical, no overlap, partial overlap
  - Hungarian matching: full match, partial, empty inputs
  - ByteTracker: lifecycle (NEW→TRACKED→LOST→REMOVED), occlusion, re-ID
  - TrackingService: multi-camera isolation, reset, status
  - Position: foot-center calculation, normalization

No GPU, no ultralytics required.
"""
from __future__ import annotations

import sys
import types
import math
from unittest.mock import MagicMock

import pytest
import numpy as np

# ── Mock only the ML/CV deps that tracking_service doesn't need ────────────────
# DO NOT mock numpy — scipy.optimize depends on the real numpy
for mod in ["torch", "ultralytics", "cv2"]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

from app.services.tracking_models import (
    KalmanBBoxState, Position, STrack, TrackState,
    VisitorEvent, VisitorEventType, VisitorIDGenerator,
    TrackingFrame, TrackedVisitor,
)
from app.services.tracking_service import (
    ByteTracker, KalmanFilter, TrackingService,
    iou_batch, hungarian_match,
)
from app.services.detection_models import BoundingBox, Detection


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_detection(x1=100, y1=100, x2=200, y2=300, conf=0.85, cam="cam-1") -> Detection:
    return Detection(
        class_id=0, class_name="person", confidence=conf,
        bounding_box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
        timestamp=1_700_000_000.0, camera_id=cam,
    )


def make_id_gen() -> VisitorIDGenerator:
    return VisitorIDGenerator()


# ── VisitorIDGenerator ────────────────────────────────────────────────────────

class TestVisitorIDGenerator:
    def test_starts_at_101(self):
        gen = make_id_gen()
        assert gen.next_id() == 101

    def test_sequential(self):
        gen = make_id_gen()
        ids = [gen.next_id() for _ in range(5)]
        assert ids == [101, 102, 103, 104, 105]

    def test_format(self):
        assert VisitorIDGenerator.format(101) == "Visitor #101"
        assert VisitorIDGenerator.format(999) == "Visitor #999"

    def test_reset(self):
        gen = make_id_gen()
        gen.next_id(); gen.next_id()
        gen.reset()
        assert gen.next_id() == 101

    def test_total_issued(self):
        gen = make_id_gen()
        gen.next_id(); gen.next_id(); gen.next_id()
        assert gen.total_issued == 3

    def test_total_issued_after_reset(self):
        gen = make_id_gen()
        gen.next_id(); gen.next_id()
        gen.reset()
        assert gen.total_issued == 0


# ── KalmanFilter ──────────────────────────────────────────────────────────────

class TestKalmanFilter:
    def _kf(self):
        return KalmanFilter()

    def test_initiate_state_shape(self):
        kf    = self._kf()
        state = kf.initiate(np.array([100.0, 100.0, 200.0, 300.0]))
        assert state.mean.shape      == (8,)
        assert state.covariance.shape == (8, 8)

    def test_initiate_center_correct(self):
        kf    = self._kf()
        state = kf.initiate(np.array([100.0, 100.0, 200.0, 200.0]))
        # cx=150, cy=150, w=100, h=100, velocities=0
        assert abs(state.mean[0] - 150.0) < 1e-6
        assert abs(state.mean[1] - 150.0) < 1e-6
        assert abs(state.mean[2] - 100.0) < 1e-6
        assert abs(state.mean[4]) < 1e-6   # vx = 0

    def test_predict_advances_position(self):
        kf    = self._kf()
        state = kf.initiate(np.array([0.0, 0.0, 100.0, 100.0]))
        # Manually set velocity
        state.mean[4] = 10.0    # vx = 10 px/frame
        state.mean[5] = 5.0     # vy = 5 px/frame
        predicted = kf.predict(state)
        assert abs(predicted.mean[0] - 60.0) < 1e-6   # cx + vx: 50 + 10
        assert abs(predicted.mean[1] - 55.0) < 1e-6   # cy + vy: 50 + 5

    def test_update_converges_to_measurement(self):
        kf    = self._kf()
        state = kf.initiate(np.array([0.0, 0.0, 100.0, 100.0]))
        # Update with exact same bbox — state should barely change
        updated = kf.update(state, np.array([0.0, 0.0, 100.0, 100.0]))
        assert abs(updated.mean[0] - 50.0) < 5.0    # cx ≈ 50

    def test_gating_distance_zero_for_same(self):
        kf    = self._kf()
        bbox  = np.array([0.0, 0.0, 100.0, 100.0])
        state = kf.initiate(bbox)
        dist  = kf.gating_distance(state, bbox)
        assert dist < 1e-3   # same obs → near-zero Mahalanobis dist

    def test_gating_distance_increases_with_distance(self):
        kf    = self._kf()
        bbox  = np.array([0.0, 0.0, 100.0, 100.0])
        state = kf.initiate(bbox)
        d_near = kf.gating_distance(state, bbox + 10)
        d_far  = kf.gating_distance(state, bbox + 200)
        assert d_far > d_near

    def test_covariance_grows_on_predict(self):
        kf    = self._kf()
        state = kf.initiate(np.array([0.0, 0.0, 100.0, 100.0]))
        pred  = kf.predict(state)
        assert pred.covariance[0, 0] > state.covariance[0, 0]   # uncertainty increases

    def test_to_xyxy_inverse_of_initiate(self):
        kf    = self._kf()
        orig  = np.array([100.0, 200.0, 400.0, 500.0])
        state = kf.initiate(orig)
        x1, y1, x2, y2 = state.to_xyxy()
        assert abs(x1 - 100.0) < 1e-6
        assert abs(y1 - 200.0) < 1e-6
        assert abs(x2 - 400.0) < 1e-6
        assert abs(y2 - 500.0) < 1e-6


# ── IoU batch ─────────────────────────────────────────────────────────────────

class TestIouBatch:
    def test_identical_boxes_iou_1(self):
        boxes = np.array([[0, 0, 100, 100]], dtype=float)
        result = iou_batch(boxes, boxes)
        assert result.shape == (1, 1)
        assert abs(result[0, 0] - 1.0) < 1e-6

    def test_no_overlap_iou_0(self):
        a = np.array([[0, 0, 50, 50]], dtype=float)
        b = np.array([[100, 100, 200, 200]], dtype=float)
        result = iou_batch(a, b)
        assert abs(result[0, 0]) < 1e-6

    def test_half_overlap(self):
        a = np.array([[0, 0, 100, 100]], dtype=float)
        b = np.array([[50, 0, 150, 100]], dtype=float)
        result = iou_batch(a, b)
        # intersection=50*100=5000, union=100*100+100*100-5000=15000
        assert abs(result[0, 0] - 5000/15000) < 1e-4

    def test_batch_shape(self):
        a = np.random.rand(5, 4).astype(float)
        a[:, 2:] += a[:, :2] + 1   # ensure x2>x1, y2>y1
        b = np.random.rand(3, 4).astype(float)
        b[:, 2:] += b[:, :2] + 1
        result = iou_batch(a, b)
        assert result.shape == (5, 3)

    def test_iou_symmetry(self):
        a = np.array([[10, 20, 80, 90]], dtype=float)
        b = np.array([[50, 50, 120, 130]], dtype=float)
        assert abs(iou_batch(a, b)[0, 0] - iou_batch(b, a)[0, 0]) < 1e-6


# ── Hungarian matching ────────────────────────────────────────────────────────

class TestHungarianMatch:
    def test_perfect_match(self):
        cost = np.array([[0.1, 0.9], [0.9, 0.1]])
        matches, unmatched_r, unmatched_c = hungarian_match(cost, threshold=0.5)
        assert (0, 0) in matches
        assert (1, 1) in matches
        assert len(unmatched_r) == 0
        assert len(unmatched_c) == 0

    def test_no_match_above_threshold(self):
        cost = np.ones((2, 2))   # all costs = 1.0
        matches, unmatched_r, unmatched_c = hungarian_match(cost, threshold=0.5)
        assert len(matches) == 0
        assert len(unmatched_r) == 2
        assert len(unmatched_c) == 2

    def test_empty_inputs(self):
        cost = np.empty((0, 3))
        matches, unmatched_r, unmatched_c = hungarian_match(cost, threshold=0.5)
        assert matches == []
        assert unmatched_r == []
        assert len(unmatched_c) == 3

    def test_more_tracks_than_dets(self):
        cost = np.array([[0.1, 0.9, 0.9]])   # 1 track vs 3 dets
        matches, unmatched_r, unmatched_c = hungarian_match(cost, threshold=0.5)
        assert len(matches) == 1
        assert matches[0] == (0, 0)
        assert 1 in unmatched_c and 2 in unmatched_c


# ── ByteTracker lifecycle ─────────────────────────────────────────────────────

class TestByteTracker:
    def _tracker(self, min_hits=3, max_lost=5) -> ByteTracker:
        gen = make_id_gen()
        return ByteTracker(
            camera_id="cam-1",
            id_generator=gen,
            high_thresh=0.60,
            low_thresh=0.10,
            match_thresh=0.50,
            max_lost=max_lost,
            min_hits=min_hits,
        )

    def _det(self, x1=100, y1=100, x2=200, y2=300, conf=0.85) -> Detection:
        return make_detection(x1, y1, x2, y2, conf)

    def test_new_track_created(self):
        tracker = self._tracker(min_hits=1)
        active, events = tracker.update([self._det()], 1000.0, (480, 640))
        assert len(active) == 1

    def test_visitor_id_assigned(self):
        tracker = self._tracker(min_hits=1)
        active, _ = tracker.update([self._det()], 1000.0, (480, 640))
        assert active[0].visitor_id == 101

    def test_track_persists_across_frames(self):
        tracker = self._tracker(min_hits=1)
        for i in range(5):
            active, _ = tracker.update([self._det()], float(1000 + i), (480, 640))
        assert len(active) == 1
        assert active[0].visitor_id == 101
        assert active[0].age >= 5

    def test_new_to_tracked_after_min_hits(self):
        tracker = self._tracker(min_hits=3)
        states = []
        for i in range(4):
            active, _ = tracker.update([self._det()], float(1000 + i), (480, 640))
            if active:
                states.append(active[0].state)
        # After 3 hits → should have TRACKED state
        assert TrackState.TRACKED in states

    def test_enter_event_emitted_on_confirmation(self):
        tracker = self._tracker(min_hits=3)
        all_events = []
        # Need min_hits=3 detections to confirm; run 5 frames to be sure
        for i in range(5):
            _, events = tracker.update([self._det()], float(1000 + i), (480, 640))
            all_events.extend(events)
        enter_events = [e for e in all_events if e.event_type == VisitorEventType.ENTER]
        assert len(enter_events) >= 1

    def test_track_goes_lost_when_undetected(self):
        tracker = self._tracker(min_hits=1, max_lost=10)
        tracker.update([self._det()], 1000.0, (480, 640))
        # 3 frames with no detection
        for i in range(3):
            active, _ = tracker.update([], float(1001 + i), (480, 640))
        # Track should be LOST (not REMOVED yet)
        all_tracks = tracker._tracks
        assert any(t.state == TrackState.LOST for t in all_tracks)

    def test_track_removed_after_max_lost(self):
        tracker = self._tracker(min_hits=1, max_lost=3)
        tracker.update([self._det()], 1000.0, (480, 640))
        # 5 frames with no detection (> max_lost=3)
        all_events = []
        for i in range(5):
            _, events = tracker.update([], float(1001 + i), (480, 640))
            all_events.extend(events)
        assert len(tracker._tracks) == 0
        exit_events = [e for e in all_events if e.event_type == VisitorEventType.EXIT]
        assert len(exit_events) == 1

    def test_reacquired_after_brief_loss(self):
        tracker = self._tracker(min_hits=1, max_lost=10)
        # Detect in frame 1
        tracker.update([self._det()], 1000.0, (480, 640))
        # Gone for 2 frames
        tracker.update([], 1001.0, (480, 640))
        tracker.update([], 1002.0, (480, 640))
        # Reappears — same position → should reacquire
        _, events = tracker.update([self._det()], 1003.0, (480, 640))
        reacquired = [e for e in events if e.event_type == VisitorEventType.REACQUIRED]
        assert len(reacquired) == 1

    def test_visitor_id_preserved_after_reacquire(self):
        tracker = self._tracker(min_hits=1, max_lost=10)
        active, _ = tracker.update([self._det()], 1000.0, (480, 640))
        vid_before = active[0].visitor_id
        tracker.update([], 1001.0, (480, 640))
        tracker.update([], 1002.0, (480, 640))
        active, _ = tracker.update([self._det()], 1003.0, (480, 640))
        if active:
            assert active[0].visitor_id == vid_before

    def test_two_distinct_visitors_get_different_ids(self):
        tracker = self._tracker(min_hits=1)
        # Two far-apart detections → two distinct tracks
        d1 = self._det(x1=10,  y1=10,  x2=80,  y2=200)
        d2 = self._det(x1=500, y1=300, x2=580, y2=480)
        active, _ = tracker.update([d1, d2], 1000.0, (480, 640))
        assert len(active) == 2
        assert active[0].visitor_id != active[1].visitor_id

    def test_low_conf_detection_helps_reacquire(self):
        tracker = self._tracker(min_hits=1, max_lost=10)
        tracker.update([self._det(conf=0.85)], 1000.0, (480, 640))
        # Low-confidence detection while LOST → should reacquire
        tracker.update([], 1001.0, (480, 640))
        low_conf_det = self._det(conf=0.15)  # below high_thresh
        _, events = tracker.update([low_conf_det], 1002.0, (480, 640))
        reacquired = [e for e in events if e.event_type == VisitorEventType.REACQUIRED]
        assert len(reacquired) == 1

    def test_reset_clears_all_tracks(self):
        tracker = self._tracker(min_hits=1)
        tracker.update([self._det()], 1000.0, (480, 640))
        tracker.reset()
        assert len(tracker._tracks) == 0
        assert tracker._frame_idx == 0


# ── Position ──────────────────────────────────────────────────────────────────

class TestPosition:
    def test_foot_center_correct(self):
        pos = Position.from_bbox(100, 50, 300, 400, frame_w=640, frame_h=480)
        assert pos.x == 200.0    # (100+300)/2
        assert pos.y == 400.0    # y2 (bottom)

    def test_norm_clamped(self):
        pos = Position.from_bbox(0, 0, 640, 480, frame_w=640, frame_h=480)
        assert pos.x_norm <= 1.0
        assert pos.y_norm <= 1.0

    def test_to_dict(self):
        pos = Position.from_bbox(0, 0, 100, 100, frame_w=640, frame_h=480)
        d = pos.to_dict()
        assert "x" in d and "y" in d and "x_norm" in d and "y_norm" in d


# ── TrackingService ───────────────────────────────────────────────────────────

class TestTrackingService:
    def test_separate_trackers_per_camera(self):
        svc  = TrackingService(min_hits=1)
        det1 = make_detection(cam="cam-a")
        det2 = make_detection(cam="cam-b")
        svc.process("cam-a", [det1], 1000.0, 0, (480, 640))
        svc.process("cam-b", [det2], 1000.0, 0, (480, 640))
        assert svc.get_tracker("cam-a") is not svc.get_tracker("cam-b")

    def test_visitor_ids_globally_unique(self):
        svc = TrackingService(min_hits=1)
        f1, _ = svc.process("cam-a", [make_detection(cam="cam-a")], 1000.0, 0, (480, 640))
        f2, _ = svc.process("cam-b", [make_detection(cam="cam-b")], 1000.0, 0, (480, 640))
        ids_a = {v.visitor_id for v in f1.tracked}
        ids_b = {v.visitor_id for v in f2.tracked}
        assert ids_a.isdisjoint(ids_b)  # no shared IDs across cameras

    def test_reset_camera(self):
        svc = TrackingService(min_hits=1)
        svc.process("cam-x", [make_detection()], 1000.0, 0, (480, 640))
        svc.reset_camera("cam-x")
        tracker = svc.get_tracker("cam-x")
        assert len(tracker._tracks) == 0

    def test_status_output(self):
        svc    = TrackingService()
        status = svc.get_status()
        assert "total_visitors_issued" in status
        assert "active_cameras"        in status

    def test_returns_tracking_frame(self):
        svc   = TrackingService(min_hits=1)
        frame, events = svc.process("cam-1", [make_detection()], 1000.0, 0, (480, 640))
        assert isinstance(frame, TrackingFrame)
        assert frame.camera_id == "cam-1"

    def test_empty_detections_handled(self):
        svc   = TrackingService()
        frame, events = svc.process("cam-1", [], 1000.0, 0, (480, 640))
        assert frame.visible_count == 0
        assert events == []
