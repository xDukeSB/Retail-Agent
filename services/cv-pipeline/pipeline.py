"""
Main camera pipeline — orchestrates stream reading, detection, tracking, and event publishing.
"""
import asyncio
import logging
import time
from datetime import datetime, date, timezone
from typing import Dict, List, Optional

import cv2
import numpy as np

from config import PipelineConfig
from detector import PersonDetector
from tracker import PersonTracker, TrackedPerson
from zone_manager import ZoneManager
from heatmap_accumulator import HeatmapAccumulator
from event_publisher import EventPublisher

logger = logging.getLogger("cv-pipeline.pipeline")


class CameraPipeline:
    """
    Full CV pipeline for a single camera.
    Runs: read frame → detect → track → zone check → publish events → accumulate heatmap
    """

    def __init__(self, camera_id: str, config: PipelineConfig):
        self.camera_id = camera_id
        self.config = config
        self.detector = PersonDetector(
            config.model_path, config.confidence_threshold, config.device
        )
        self.tracker = PersonTracker(
            config.track_thresh, config.track_buffer, config.match_thresh, config.target_fps
        )
        self.zone_manager = ZoneManager(throttle_seconds=config.zone_event_throttle)
        self.heatmap = HeatmapAccumulator(config.heatmap_grid_size)
        self.publisher = EventPublisher(config.backend_url, camera_id)

        # Track entry times for dwell calculation
        self._track_entry_times: Dict[int, float] = {}
        self._track_zones: Dict[int, List[str]] = {}
        self._prev_positions: Dict[int, tuple] = {}

    async def run(self, stop_event: asyncio.Event):
        """Main pipeline loop."""
        logger.info(f"Pipeline starting for camera: {self.camera_id}")
        self.detector.load()
        self.tracker.load()

        async with self.publisher as pub:
            await pub.update_camera_status("connecting")
            cap = await self._open_stream()
            if cap is None:
                await pub.update_camera_status("error")
                return

            await pub.update_camera_status("active")
            await self._fetch_zone_config(pub)

            frame_interval = 1.0 / self.config.target_fps
            last_heatmap_push = time.time()
            last_queue_check = time.time()

            try:
                while not stop_event.is_set():
                    loop_start = time.time()

                    ret, frame = cap.read()
                    if not ret:
                        logger.warning("Stream read failed — reconnecting...")
                        await pub.update_camera_status("connecting")
                        await asyncio.sleep(3)
                        cap = await self._open_stream()
                        if cap is None:
                            break
                        await pub.update_camera_status("active")
                        continue

                    h, w = frame.shape[:2]
                    ts = time.time()

                    # Detect + track
                    detections = self.detector.detect(frame)
                    active_tracks, new_ids, lost_ids = self.tracker.update(
                        detections, w, h, ts
                    )

                    # Handle new tracks
                    for tid in new_ids:
                        self._track_entry_times[tid] = ts
                        self._track_zones[tid] = []
                        track = self.tracker.get_track(tid)
                        if track:
                            await pub.track_start(tid, track.x, track.y, ts)

                    # Handle lost tracks
                    for tid in lost_ids:
                        entry_time = self._track_entry_times.pop(tid, ts)
                        dwell = ts - entry_time
                        zones_visited = self._track_zones.pop(tid, [])
                        lost_track = self.tracker.get_track(tid)
                        path = []
                        if lost_track:
                            path = [[p[0], p[1], p[2]] for p in lost_track.path[-200:]]
                        await pub.track_end(
                            tid, entry_time, ts, dwell, zones_visited, path
                        )
                        self.zone_manager.cleanup_track(tid)
                        self._prev_positions.pop(tid, None)

                    # Update active tracks
                    all_positions = []
                    for person in active_tracks:
                        prev = self._prev_positions.get(person.track_id)
                        prev_x = prev[0] if prev else None
                        prev_y = prev[1] if prev else None

                        # Zone detection
                        crossings = self.zone_manager.update(
                            person.track_id, person.x, person.y, prev_x, prev_y, ts
                        )
                        for crossing in crossings:
                            if crossing.zone_name not in self._track_zones.get(person.track_id, []):
                                self._track_zones.setdefault(person.track_id, []).append(crossing.zone_name)
                            await pub.zone_crossing(
                                person.track_id,
                                crossing.zone_name,
                                crossing.zone_type,
                                crossing.event_type,
                                crossing.x,
                                crossing.y,
                                ts,
                            )

                        self._prev_positions[person.track_id] = (person.x, person.y)
                        all_positions.append((person.x, person.y))

                    # Accumulate heatmap
                    self.heatmap.add_batch(all_positions)

                    # Push heatmap batch periodically
                    if self.heatmap.should_flush(self.config.heatmap_push_interval_seconds):
                        cells = self.heatmap.get_cells_for_export()
                        today = date.today().isoformat()
                        await pub.push_heatmap(today, cells)
                        self.heatmap.reset()

                    # Sleep to maintain target FPS
                    elapsed = time.time() - loop_start
                    sleep_time = max(0, frame_interval - elapsed)
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                pass
            finally:
                cap.release()
                await pub.update_camera_status("inactive")
                logger.info(f"Pipeline stopped for camera: {self.camera_id}")

    async def _open_stream(self, retries: int = 5) -> Optional[cv2.VideoCapture]:
        """Opens the RTSP stream with retries."""
        rtsp_url = self.config.rtsp_url
        for attempt in range(retries):
            cap = cv2.VideoCapture(rtsp_url)
            if cap.isOpened():
                # Set buffer size to minimize latency
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                logger.info(f"Stream opened: {rtsp_url}")
                return cap
            logger.warning(f"Stream open failed (attempt {attempt+1}/{retries}): {rtsp_url}")
            await asyncio.sleep(3)
        logger.error(f"Could not open stream after {retries} attempts: {rtsp_url}")
        return None

    async def _fetch_zone_config(self, pub: EventPublisher):
        """Fetch zone config from backend and load into zone manager."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.config.backend_url}/api/cameras/{self.camera_id}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    zone_config = data.get("zone_config")
                    if zone_config:
                        import json
                        self.zone_manager.load_config(json.dumps(zone_config))
                        logger.info(f"Loaded zone config for camera {self.camera_id}")
        except Exception as e:
            logger.warning(f"Could not fetch zone config: {e}")
