"""
ByteTrack-based anonymous person tracker.
Track IDs are ephemeral (reset per session) — never linked to identity.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from detector import Detection

logger = logging.getLogger("cv-pipeline.tracker")


@dataclass
class TrackedPerson:
    """Anonymous tracked person — centroid + ephemeral ID only."""
    track_id: int
    x: float  # normalized 0-1
    y: float  # normalized 0-1
    confidence: float
    age: int = 0  # frames since first seen
    frames_missing: int = 0
    path: List[Tuple[float, float, float]] = field(default_factory=list)  # [(x, y, ts)]

    @property
    def centroid(self) -> Tuple[float, float]:
        return (self.x, self.y)


class PersonTracker:
    """
    Wraps supervision ByteTrack for anonymous person tracking.
    Privacy: track IDs are integers that reset every pipeline session.
    """

    def __init__(self, track_thresh: float, track_buffer: int, match_thresh: float, fps: int):
        self.track_thresh = track_thresh
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.fps = fps
        self._tracker = None
        self._active: Dict[int, TrackedPerson] = {}
        logger.info("PersonTracker initialized (ByteTrack)")

    def load(self):
        """Initialize ByteTrack."""
        try:
            import supervision as sv
            self._tracker = sv.ByteTrack(
                track_activation_threshold=self.track_thresh,
                lost_track_buffer=self.track_buffer,
                minimum_matching_threshold=self.match_thresh,
                frame_rate=self.fps,
            )
            logger.info("ByteTrack loaded")
        except Exception as e:
            logger.error(f"Failed to load ByteTrack: {e}")
            raise

    def update(
        self,
        detections: List[Detection],
        frame_width: int,
        frame_height: int,
        timestamp: float,
    ) -> Tuple[List[TrackedPerson], List[int], List[int]]:
        """
        Update tracker with current frame detections.
        Returns: (active_tracks, new_track_ids, lost_track_ids)
        """
        import supervision as sv

        if not detections:
            # Update tracker with empty detections to handle lost tracks
            sv_detections = sv.Detections.empty()
        else:
            # Convert to supervision format (pixel coords for tracker)
            boxes = np.array([
                [d.x1 * frame_width, d.y1 * frame_height,
                 d.x2 * frame_width, d.y2 * frame_height]
                for d in detections
            ], dtype=np.float32)
            confidences = np.array([d.confidence for d in detections], dtype=np.float32)
            class_ids = np.zeros(len(detections), dtype=int)

            sv_detections = sv.Detections(
                xyxy=boxes,
                confidence=confidences,
                class_id=class_ids,
            )

        tracked = self._tracker.update_with_detections(sv_detections)

        current_ids = set()
        active_tracks = []
        new_ids = []

        for i in range(len(tracked)):
            track_id = int(tracked.tracker_id[i])
            box = tracked.xyxy[i]
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.5

            # Centroid normalized
            cx = ((box[0] + box[2]) / 2) / frame_width
            cy = ((box[1] + box[3]) / 2) / frame_height

            current_ids.add(track_id)

            if track_id not in self._active:
                new_ids.append(track_id)
                self._active[track_id] = TrackedPerson(
                    track_id=track_id,
                    x=cx, y=cy,
                    confidence=conf,
                )

            person = self._active[track_id]
            person.x = cx
            person.y = cy
            person.confidence = conf
            person.age += 1
            person.frames_missing = 0
            person.path.append((cx, cy, timestamp))

            # Keep path bounded to last 1000 points
            if len(person.path) > 1000:
                person.path = person.path[-1000:]

            active_tracks.append(person)

        # Detect lost tracks
        lost_ids = []
        for tid in list(self._active.keys()):
            if tid not in current_ids:
                self._active[tid].frames_missing += 1
                if self._active[tid].frames_missing > self.track_buffer:
                    lost_ids.append(tid)
                    del self._active[tid]

        return active_tracks, new_ids, lost_ids

    def get_track(self, track_id: int) -> Optional[TrackedPerson]:
        return self._active.get(track_id)

    def get_all_active(self) -> List[TrackedPerson]:
        return list(self._active.values())
