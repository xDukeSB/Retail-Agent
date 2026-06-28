"""
tracking_service.py — ByteTrack multi-object tracking implementation.

Implements ByteTrack (Zhang et al. 2022) from scratch:
  - Kalman Filter for motion prediction (constant velocity model)
  - Hungarian algorithm (scipy linear_sum_assignment) for data association
  - Two-stage matching: high-confidence → low-confidence detections
  - Track lifecycle: NEW → TRACKED → LOST → REMOVED

One ByteTracker instance per camera — fully stateful, synchronous.
Called from TrackingPipeline which handles async dispatch.

Privacy:
  - No appearance features (ReID embeddings) — geometry-only tracking
  - Visitor IDs are anonymous sequential ints, reset on restart
  - No bounding box pixel data stored
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.core.logging import get_logger
from app.services.tracking_models import (
    KalmanBBoxState, Position, STrack, TrackState,
    TrackingFrame, TrackedVisitor, VisitorEvent,
    VisitorEventType, VisitorIDGenerator,
)

if TYPE_CHECKING:
    from app.services.detection_models import Detection

logger = get_logger(__name__)


# ── Kalman Filter ──────────────────────────────────────────────────────────────

class KalmanFilter:
    """
    Constant-velocity Kalman Filter for bounding box tracking.

    State:        [cx, cy, w, h, vx, vy, vw, vh]  (8-dim)
    Observation:  [cx, cy, w, h]                   (4-dim)

    Motion model: x_k = F · x_{k-1}
    Measurement:  z_k = H · x_k + noise
    """

    def __init__(self):
        dt = 1.0   # one timestep = one frame

        # State transition matrix (constant velocity)
        self.F = np.eye(8)
        for i in range(4):
            self.F[i, i + 4] = dt

        # Observation matrix (observe position only)
        self.H = np.eye(4, 8)

        # Process noise covariance
        self.Q = np.eye(8) * 0.01
        # Higher uncertainty for velocity components
        self.Q[4:, 4:] *= 100.0

        # Measurement noise covariance
        self.R = np.eye(4) * 1.0

    def initiate(self, bbox_xyxy: np.ndarray) -> KalmanBBoxState:
        """Create initial state from first detection (zero velocity)."""
        x1, y1, x2, y2 = bbox_xyxy
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        w  = x2 - x1
        h  = y2 - y1

        mean = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0])
        covariance = np.eye(8) * 10.0
        covariance[4:, 4:] *= 1000.0   # high initial velocity uncertainty
        return KalmanBBoxState(mean=mean, covariance=covariance)

    def predict(self, state: KalmanBBoxState) -> KalmanBBoxState:
        """Predict next position using motion model."""
        mean = self.F @ state.mean
        cov  = self.F @ state.covariance @ self.F.T + self.Q
        # Clamp covariance to prevent numerical overflow on long-lost tracks
        cov  = np.clip(cov, -1e6, 1e6)
        return KalmanBBoxState(mean=mean, covariance=cov)

    def update(self, state: KalmanBBoxState, bbox_xyxy: np.ndarray) -> KalmanBBoxState:
        """Correct prediction with observed detection."""
        x1, y1, x2, y2 = bbox_xyxy
        z = np.array([(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1])

        # Innovation
        S  = self.H @ state.covariance @ self.H.T + self.R
        K  = state.covariance @ self.H.T @ np.linalg.inv(S)    # Kalman gain
        y  = z - self.H @ state.mean                            # measurement residual

        mean = state.mean + K @ y
        cov  = (np.eye(8) - K @ self.H) @ state.covariance
        return KalmanBBoxState(mean=mean, covariance=cov)

    def gating_distance(self, state: KalmanBBoxState, bbox_xyxy: np.ndarray) -> float:
        """Mahalanobis distance between predicted state and detection."""
        x1, y1, x2, y2 = bbox_xyxy
        z     = np.array([(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1])
        S     = self.H @ state.covariance @ self.H.T + self.R
        diff  = z - self.H @ state.mean
        return float(diff @ np.linalg.inv(S) @ diff)


# ── IoU utilities ──────────────────────────────────────────────────────────────

def iou_batch(bboxes_a: np.ndarray, bboxes_b: np.ndarray) -> np.ndarray:
    """
    Vectorised IoU matrix. Both arrays shape (N, 4) with [x1, y1, x2, y2].
    Returns (N, M) IoU matrix.
    """
    area_a = (bboxes_a[:, 2] - bboxes_a[:, 0]) * (bboxes_a[:, 3] - bboxes_a[:, 1])
    area_b = (bboxes_b[:, 2] - bboxes_b[:, 0]) * (bboxes_b[:, 3] - bboxes_b[:, 1])

    ix1 = np.maximum(bboxes_a[:, None, 0], bboxes_b[None, :, 0])
    iy1 = np.maximum(bboxes_a[:, None, 1], bboxes_b[None, :, 1])
    ix2 = np.minimum(bboxes_a[:, None, 2], bboxes_b[None, :, 2])
    iy2 = np.minimum(bboxes_a[:, None, 3], bboxes_b[None, :, 3])

    inter = np.maximum(0, ix2 - ix1) * np.maximum(0, iy2 - iy1)
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / union, 0.0)


def hungarian_match(
    cost: np.ndarray,
    threshold: float,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """
    Hungarian matching on a cost matrix.
    Returns (matches, unmatched_rows, unmatched_cols).
    """
    if cost.size == 0:
        return [], list(range(cost.shape[0])), list(range(cost.shape[1]))

    row_idx, col_idx = linear_sum_assignment(cost)
    matches, unmatched_rows, unmatched_cols = [], [], []
    matched_rows, matched_cols = set(), set()

    for r, c in zip(row_idx, col_idx):
        if cost[r, c] <= threshold:
            matches.append((r, c))
            matched_rows.add(r)
            matched_cols.add(c)

    for r in range(cost.shape[0]):
        if r not in matched_rows:
            unmatched_rows.append(r)
    for c in range(cost.shape[1]):
        if c not in matched_cols:
            unmatched_cols.append(c)

    return matches, unmatched_rows, unmatched_cols


# ── ByteTracker ────────────────────────────────────────────────────────────────

class ByteTracker:
    """
    ByteTrack implementation for a single camera.

    Two-stage matching:
      Stage 1 — high-confidence detections (≥ high_thresh) vs ALL active tracks
      Stage 2 — low-confidence detections  (< high_thresh) vs LOST tracks only

    This is the key ByteTrack innovation: low-confidence detections are still
    useful for re-identifying tracks during occlusion.
    """

    def __init__(
        self,
        camera_id: str,
        id_generator: VisitorIDGenerator,
        high_thresh: float = 0.60,
        low_thresh:  float = 0.10,
        match_thresh: float = 0.80,    # IoU threshold for matching
        max_lost:    int   = 30,       # frames before track removed
        min_hits:    int   = 3,        # frames before NEW → TRACKED
    ):
        self.camera_id    = camera_id
        self._id_gen      = id_generator
        self.high_thresh  = high_thresh
        self.low_thresh   = low_thresh
        self.match_thresh = match_thresh
        self.max_lost     = max_lost
        self.min_hits     = min_hits

        self._kf          = KalmanFilter()
        self._tracks:     list[STrack] = []
        self._next_tid    = 1           # internal ByteTrack track ID
        self._frame_idx   = 0

        # Events emitted this update cycle
        self._pending_events: list[VisitorEvent] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(
        self,
        detections: list["Detection"],
        timestamp: float,
        frame_shape: tuple[int, int],
    ) -> tuple[list[STrack], list[VisitorEvent]]:
        """
        Core ByteTrack update step.
        Called once per frame with all person detections.
        Returns (active_tracks, events_this_frame).
        """
        self._frame_idx       += 1
        self._pending_events   = []
        h, w                   = frame_shape

        # Separate high / low confidence detections
        dets_high = [d for d in detections if d.confidence >= self.high_thresh]
        dets_low  = [d for d in detections if self.low_thresh <= d.confidence < self.high_thresh]

        # Split existing tracks
        tracked  = [t for t in self._tracks if t.state == TrackState.TRACKED]
        lost     = [t for t in self._tracks if t.state == TrackState.LOST]
        new_trks = [t for t in self._tracks if t.state == TrackState.NEW]

        # ── Kalman predict all active tracks ──────────────────────────────────
        for t in tracked + lost + new_trks:
            t.kalman = self._kf.predict(t.kalman)
            t.age   += 1

        # ── Stage 1: match high-conf dets vs ALL active tracks (tracked+new+lost) ─
        candidates_1  = tracked + new_trks + lost
        matches_1, unmatched_tracks_1, unmatched_dets_high = self._iou_match(
            candidates_1, dets_high, self.match_thresh
        )

        matched_track_ids_1 = {m[0] for m in matches_1}

        for ti, di in matches_1:
            t   = candidates_1[ti]
            det = dets_high[di]
            t.kalman = self._kf.update(t.kalman, self._det_xyxy(det))
            was_lost = t.state == TrackState.LOST
            if t.state == TrackState.NEW:
                t.mark_hit(det.confidence, timestamp)    # accumulate hits, no promotion yet
            else:
                t.mark_tracked(det.confidence, timestamp)
            if was_lost:
                self._emit_event(VisitorEventType.REACQUIRED, t, timestamp)

        # ── Stage 2: match low-conf dets vs LOST tracks ────────────────────────
        unmatched_lost  = [t for t in lost]   # all lost tracks
        matches_2, unmatched_lost_2, _ = self._iou_match(
            unmatched_lost, dets_low, self.match_thresh
        )

        matched_lost_ids_2 = {m[0] for m in matches_2}

        for ti, di in matches_2:
            t   = unmatched_lost[ti]
            det = dets_low[di]
            t.kalman = self._kf.update(t.kalman, self._det_xyxy(det))
            t.mark_tracked(det.confidence, timestamp)
            self._emit_event(VisitorEventType.REACQUIRED, t, timestamp)

        # ── Mark unmatched tracked/new as LOST ────────────────────────────────
        for ti, t in enumerate(candidates_1):
            if ti not in matched_track_ids_1:
                t.mark_lost()

        # Tracks in lost that were unmatched in Stage 2 → increment lost
        for ti, t in enumerate(unmatched_lost):
            if ti not in matched_lost_ids_2:
                t.mark_lost()

        # ── Create new tracks from unmatched high-conf detections ──────────────
        for di in unmatched_dets_high:
            det    = dets_high[di]
            new_t  = self._new_track(det, timestamp)
            self._tracks.append(new_t)

        # ── Promote NEW → TRACKED after min_hits ─────────────────────────────
        for t in self._tracks:
            if t.state == TrackState.NEW and t.hits >= self.min_hits:
                t.state = TrackState.TRACKED
                self._emit_event(VisitorEventType.ENTER, t, timestamp)

        # ── Remove expired lost tracks ─────────────────────────────────────────
        for t in self._tracks:
            if t.state == TrackState.LOST and t.time_since_update > self.max_lost:
                t.mark_removed()
                self._emit_event(VisitorEventType.EXIT, t, timestamp,
                                 dwell_seconds=timestamp - t.start_ts)

        # ── Prune removed tracks ───────────────────────────────────────────────
        self._tracks = [t for t in self._tracks if t.state != TrackState.REMOVED]

        active = [t for t in self._tracks if t.state in (TrackState.TRACKED, TrackState.NEW)]
        return active, list(self._pending_events)

    def build_tracking_frame(
        self,
        active: list[STrack],
        timestamp: float,
        frame_idx: int,
        frame_shape: tuple[int, int],
        processing_ms: float,
    ) -> TrackingFrame:
        """Convert active STrack list → TrackingFrame Pydantic model."""
        h, w = frame_shape
        visitors: list[TrackedVisitor] = []

        for t in active:
            x1, y1, x2, y2 = t.xyxy
            visitors.append(TrackedVisitor(
                visitor_id=t.visitor_id,
                visitor_label=VisitorIDGenerator.format(t.visitor_id),
                track_id=t.track_id,
                state=t.state,
                confidence=t.confidence,
                age=t.age,
                time_since_update=t.time_since_update,
                position=Position.from_bbox(x1, y1, x2, y2, frame_w=w, frame_h=h),
                bbox=[round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                timestamp=timestamp,
                camera_id=self.camera_id,
                class_id=t.class_id,
            ))

        lost_count = sum(1 for t in self._tracks if t.state == TrackState.LOST)
        return TrackingFrame(
            camera_id=self.camera_id,
            timestamp=timestamp,
            frame_idx=frame_idx,
            frame_shape=frame_shape,
            tracked=visitors,
            lost_count=lost_count,
            total_active=len(active) + lost_count,
            processing_ms=processing_ms,
        )

    def reset(self) -> None:
        """Clear all tracks (e.g. camera restarted)."""
        self._tracks.clear()
        self._frame_idx = 0
        logger.info("ByteTracker reset", extra={"camera_id": self.camera_id})

    @property
    def track_count(self) -> int:
        return len(self._tracks)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _iou_match(
        self,
        tracks: list[STrack],
        detections: list["Detection"],
        threshold: float,
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        """Build IoU cost matrix and run Hungarian matching."""
        if not tracks or not detections:
            return [], list(range(len(tracks))), list(range(len(detections)))

        track_boxes = np.array([list(t.xyxy) for t in tracks], dtype=np.float32)
        det_boxes   = np.array([self._det_xyxy(d) for d in detections], dtype=np.float32)
        iou         = iou_batch(track_boxes, det_boxes)
        cost        = 1.0 - iou   # convert similarity → cost
        return hungarian_match(cost, 1.0 - threshold)

    @staticmethod
    def _det_xyxy(det: "Detection") -> np.ndarray:
        bb = det.bounding_box
        return np.array([bb.x1, bb.y1, bb.x2, bb.y2], dtype=np.float32)

    def _new_track(self, det: "Detection", timestamp: float) -> STrack:
        tid = self._next_tid
        self._next_tid += 1
        vid = self._id_gen.next_id()
        ks  = self._kf.initiate(self._det_xyxy(det))
        return STrack(
            track_id=tid,
            visitor_id=vid,
            state=TrackState.NEW,
            kalman=ks,
            confidence=det.confidence,
            start_ts=timestamp,
            last_ts=timestamp,
            class_id=det.class_id,
        )

    def _emit_event(
        self,
        event_type: VisitorEventType,
        track: STrack,
        timestamp: float,
        dwell_seconds: float = 0.0,
    ) -> None:
        x1, y1, x2, y2 = track.xyxy
        # We don't have frame_shape here — use None for position in events
        self._pending_events.append(VisitorEvent(
            event_type=event_type,
            visitor_id=track.visitor_id,
            visitor_label=VisitorIDGenerator.format(track.visitor_id),
            track_id=track.track_id,
            camera_id=self.camera_id,
            timestamp=timestamp,
            dwell_seconds=dwell_seconds,
        ))


# ── TrackingService (multi-camera) ────────────────────────────────────────────

class TrackingService:
    """
    Manages one ByteTracker per camera.
    Shared VisitorIDGenerator ensures globally unique visitor IDs
    across all cameras in a session.
    """

    def __init__(
        self,
        high_thresh: float = 0.60,
        low_thresh:  float = 0.10,
        match_thresh: float = 0.80,
        max_lost:    int   = 30,
        min_hits:    int   = 3,
    ):
        self._id_gen      = VisitorIDGenerator()
        self._trackers:   dict[str, ByteTracker] = {}
        self._config      = dict(
            high_thresh=high_thresh,
            low_thresh=low_thresh,
            match_thresh=match_thresh,
            max_lost=max_lost,
            min_hits=min_hits,
        )

    def get_tracker(self, camera_id: str) -> ByteTracker:
        if camera_id not in self._trackers:
            self._trackers[camera_id] = ByteTracker(
                camera_id=camera_id,
                id_generator=self._id_gen,
                **self._config,
            )
            logger.info("ByteTracker created", extra={"camera_id": camera_id})
        return self._trackers[camera_id]

    def process(
        self,
        camera_id: str,
        detections: list["Detection"],
        timestamp: float,
        frame_idx: int,
        frame_shape: tuple[int, int],
    ) -> tuple[TrackingFrame, list[VisitorEvent]]:
        """
        Process one frame's detections for a camera.
        Returns (TrackingFrame, events).
        Thread-safe per camera (each tracker is independent).
        """
        t0      = time.perf_counter()
        tracker = self.get_tracker(camera_id)

        # Filter to person-class only for tracking
        person_dets = [d for d in detections if d.class_id == 0]

        active, events = tracker.update(person_dets, timestamp, frame_shape)
        ms     = (time.perf_counter() - t0) * 1000
        frame  = tracker.build_tracking_frame(active, timestamp, frame_idx, frame_shape, ms)
        return frame, events

    def reset_camera(self, camera_id: str) -> None:
        if camera_id in self._trackers:
            self._trackers[camera_id].reset()

    def remove_camera(self, camera_id: str) -> None:
        self._trackers.pop(camera_id, None)

    def get_status(self) -> dict:
        return {
            "total_visitors_issued": self._id_gen.total_issued,
            "active_cameras":        len(self._trackers),
            "camera_track_counts": {
                cid: t.track_count for cid, t in self._trackers.items()
            },
        }


# Singleton
tracking_service = TrackingService()
