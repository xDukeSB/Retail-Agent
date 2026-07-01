import logging
import time
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any

from sqlalchemy import select, update

from database import AsyncSessionLocal
from models.camera import Camera
from models.track import PersonTrack
from models.event import ZoneEvent
from models.analytics import HeatmapCell

from .zone_manager import ZoneManager
from .heatmap_accumulator import HeatmapAccumulator

logger = logging.getLogger("retailai.analytics_tracker")

class AnalyticsTracker:
    def __init__(self):
        # camera_id -> dict of track_id -> { "entry_time": datetime, "path_json": [], "zones_visited": set(), "last_seen": float, "db_uuid": str }
        self._active_tracks: Dict[str, Dict[int, Dict]] = {}
        # camera_id -> ZoneManager
        self._zone_managers: Dict[str, ZoneManager] = {}
        # camera_id -> last zone reload timestamp (epoch float)
        self._zone_last_loaded: Dict[str, float] = {}
        # How often to re-check DB for new zones (seconds)
        self._zone_reload_interval: float = 30.0
        # camera_id -> HeatmapAccumulator
        self._heatmaps: Dict[str, HeatmapAccumulator] = {}
        # camera_id -> List[dict] — zone crossings from last processed frame
        # Consumed by TransactionEngine via get_last_frame_crossings()
        self._last_frame_crossings: Dict[str, List[dict]] = {}

    async def _ensure_camera_state(self, camera_id: str):
        if camera_id not in self._active_tracks:
            self._active_tracks[camera_id] = {}
            
        if camera_id not in self._heatmaps:
            self._heatmaps[camera_id] = HeatmapAccumulator(grid_size=100)
            
        # Load zone manager config on first use, then reload every 30s to pick up
        # new zones created via the UI without requiring a backend restart.
        now = time.time()
        needs_reload = (
            camera_id not in self._zone_managers
            or now - self._zone_last_loaded.get(camera_id, 0) > self._zone_reload_interval
        )
        if needs_reload:
            try:
                async with AsyncSessionLocal() as db:
                    cam = await db.get(Camera, camera_id)
                    zm = ZoneManager(throttle_seconds=2.0)
                    if cam and cam.zone_config:
                        zm.load_config(cam.zone_config)
                        logger.info(
                            f"[AnalyticsTracker] Reloaded zone config for camera {camera_id}"
                        )
                    # Preserve existing per-person zone state when reloading
                    if camera_id in self._zone_managers:
                        zm._person_zone_state = self._zone_managers[camera_id]._person_zone_state
                    self._zone_managers[camera_id] = zm
                    self._zone_last_loaded[camera_id] = now
            except Exception as e:
                logger.error(f"[AnalyticsTracker] Failed to reload ZoneManager: {e}")
                if camera_id not in self._zone_managers:
                    self._zone_managers[camera_id] = ZoneManager(throttle_seconds=2.0)

    async def process_frame_detections(self, camera_id: str, timestamp: float, detections: List[Dict[str, Any]]):
        """Processes live frame detections to calculate tracks, dwell, zones, and heatmap."""
        await self._ensure_camera_state(camera_id)
        
        zm = self._zone_managers[camera_id]
        hm = self._heatmaps[camera_id]
        tracks = self._active_tracks[camera_id]
        
        current_time = time.time()
        # Use provided frame timestamp for DB consistency if possible, fallback to current time
        current_dt = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()
        
        current_ids = set()
        new_tracks = []
        zone_crossings = []
        
        for det in detections:
            track_id = det.get("track_id")
            if track_id is None or track_id < 0:
                continue
                
            centroid = det.get("centroid")
            if not centroid or len(centroid) != 2:
                continue
                
            cx, cy = centroid
            current_ids.add(track_id)
            
            # Record heatmap
            hm.add_position(cx, cy)
            
            if track_id not in tracks:
                # NEW TRACK
                tracks[track_id] = {
                    "entry_time": current_dt,
                    "path_json": [],
                    "zones_visited": set(),
                    "last_seen": timestamp,
                    "db_uuid": str(uuid.uuid4())
                }
                new_tracks.append(tracks[track_id])
                
            track_data = tracks[track_id]
            track_data["last_seen"] = timestamp
            track_data["path_json"].append([cx, cy, timestamp])
            
            # Limit path length to prevent memory leaks (1000 points ~ 30-40 seconds at 30fps)
            if len(track_data["path_json"]) > 1000:
                track_data["path_json"] = track_data["path_json"][-1000:]
                
            # Check Zone Crossings
            prev_pos = track_data["path_json"][-2] if len(track_data["path_json"]) > 1 else None
            prev_x = prev_pos[0] if prev_pos else None
            prev_y = prev_pos[1] if prev_pos else None
            
            crossings = zm.update(track_id, cx, cy, prev_x, prev_y, timestamp)
            for c in crossings:
                if c.event_type == "entry":
                    track_data["zones_visited"].add(c.zone_name)
                
                zone_crossings.append({
                    "track_id": track_id,  # integer ByteTrack ID — for TransactionEngine
                    "track_uuid": track_data["db_uuid"],
                    "camera_id": camera_id,
                    "zone_name": c.zone_name,
                    "zone_type": c.zone_type,
                    "event_type": c.event_type,
                    # BUG FIX: pass as float (epoch seconds) so TransactionEngine
                    # can do arithmetic dwell calculations (ts - entry_time).
                    # The DB write below uses datetime.fromtimestamp() separately.
                    "timestamp": c.timestamp,
                    "x": c.x,
                    "y": c.y
                })
        
        # Check lost tracks (not seen for > 15 seconds)
        lost_ids = []
        for tid, tdata in tracks.items():
            if tid not in current_ids:
                if timestamp - tdata["last_seen"] > 15.0:
                    lost_ids.append(tid)

        # Cache crossings for TransactionEngine consumption
        self._last_frame_crossings[camera_id] = zone_crossings
                    
        lost_tracks = []
        for tid in lost_ids:
            lost_tracks.append(tracks.pop(tid))
            zm.cleanup_track(tid)
            
        # Push to DB asynchronously
        if new_tracks or lost_tracks or zone_crossings:
            try:
                async with AsyncSessionLocal() as db:
                    # 1. New Tracks (Insert)
                    for t in new_tracks:
                        pt = PersonTrack(
                            id=t["db_uuid"],
                            camera_id=camera_id,
                            session_track_id=0, # ephemeral
                            entry_time=t["entry_time"],
                            date=t["entry_time"].date(),
                            is_complete=False
                        )
                        db.add(pt)
                        
                    # 2. Lost Tracks (Update)
                    for t in lost_tracks:
                        exit_time = datetime.fromtimestamp(t["last_seen"])
                        dwell = (exit_time - t["entry_time"]).total_seconds()
                        if dwell < 0:
                            dwell = 0
                            
                        # Only update if exists
                        pt = await db.get(PersonTrack, t["db_uuid"])
                        if pt:
                            pt.exit_time = exit_time
                            pt.dwell_seconds = dwell
                            pt.zones_visited = json.dumps(list(t["zones_visited"]))
                            pt.path_json = json.dumps(t["path_json"])
                            pt.is_complete = True
                            
                    # 3. Zone Events (Insert)
                    for z in zone_crossings:
                        ze = ZoneEvent(
                            id=str(uuid.uuid4()),
                            track_id=z["track_uuid"],
                            camera_id=z["camera_id"],
                            zone_name=z["zone_name"],
                            zone_type=z["zone_type"],
                            event_type=z["event_type"],
                            # Convert float epoch → datetime for DB storage
                            timestamp=datetime.fromtimestamp(z["timestamp"]),
                            x=z["x"],
                            y=z["y"]
                        )
                        db.add(ze)
                        
                    await db.commit()
            except Exception as e:
                logger.error(f"[AnalyticsTracker] Failed to persist analytics: {e}")
                
        # Handle Heatmap pushing periodically (every 60 seconds)
        if hm.should_flush(interval_seconds=60):
            cells = hm.get_cells_for_export()
            if cells:
                try:
                    async with AsyncSessionLocal() as db:
                        target_date = current_dt.date()
                        for c in cells:
                            q = select(HeatmapCell).where(
                                HeatmapCell.camera_id == camera_id,
                                HeatmapCell.date == target_date,
                                HeatmapCell.cell_x == c["x"],
                                HeatmapCell.cell_y == c["y"]
                            )
                            result = await db.execute(q)
                            existing = result.scalar_one_or_none()
                            if existing:
                                existing.density += float(c.get("density", 0))
                                existing.visit_count += int(c.get("visits", 0))
                                existing.updated_at = current_dt
                            else:
                                db.add(HeatmapCell(
                                    id=str(uuid.uuid4()),
                                    camera_id=camera_id,
                                    date=target_date,
                                    cell_x=c["x"],
                                    cell_y=c["y"],
                                    density=float(c.get("density", 0)),
                                    visit_count=int(c.get("visits", 0)),
                                    updated_at=current_dt
                                ))
                        await db.commit()
                except Exception as e:
                    logger.error(f"[AnalyticsTracker] Failed to push heatmap: {e}")
            hm.reset()

    def get_last_frame_crossings(self, camera_id: str) -> List[dict]:
        """
        Returns zone crossing events from the most recently processed frame for camera_id.
        Consumed by TransactionEngine in event_engine.py.
        Each crossing dict contains:
          track_id (int), zone_name, zone_type, event_type, timestamp (datetime), x, y
        """
        return self._last_frame_crossings.get(camera_id, [])
