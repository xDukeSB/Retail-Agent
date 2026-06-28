"""
zone_analytics_service.py — Tracks visitor dwell time inside geometric zones.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.db.analytics_repository import analytics_repository
from app.db.session import AsyncSessionLocal
from app.services.tracking_models import TrackingFrame, VisitorEvent, VisitorEventType
from app.services.zone_manager import zone_manager
from app.services.zone_analytics_calculator import calculate_zone_statistics
from app.services.timeline_service import timeline_service

logger = get_logger(__name__)


class ZoneAnalyticsService:
    def __init__(self):
        # State: camera_id -> visitor_id -> zone_id -> entry_ts
        self._active_sessions: dict[str, dict[int, dict[str, float]]] = {}
        self._last_queue_time: dict[str, float] = {}

    async def start(self, tracking_pipeline) -> None:
        tracking_pipeline.add_tracking_callback(self.process_tracking_frame)
        tracking_pipeline.add_event_callback(self.process_visitor_event)
        logger.info("ZoneAnalyticsService started")

    async def stop(self, tracking_pipeline) -> None:
        tracking_pipeline.remove_tracking_callback(self.process_tracking_frame)
        tracking_pipeline.remove_event_callback(self.process_visitor_event)
        logger.info("ZoneAnalyticsService stopped")

    async def process_tracking_frame(self, frame: TrackingFrame) -> None:
        cam_id = frame.camera_id
        if cam_id not in self._active_sessions:
            self._active_sessions[cam_id] = {}

        for visitor in frame.tracked:
            vid = visitor.visitor_id
            if vid not in self._active_sessions[cam_id]:
                self._active_sessions[cam_id][vid] = {}

            # Determine which zones this visitor is currently inside
            current_zones = []
            if visitor.position:
                zones = zone_manager.get_zones_for_point(
                    cam_id, visitor.position.x_norm, visitor.position.y_norm
                )
                current_zones = [z for z in zones]

            current_zone_ids = {z.id for z in current_zones}
            active_zones_for_visitor = set(self._active_sessions[cam_id][vid].keys())

            # 1. New zones entered
            entered_zones = current_zone_ids - active_zones_for_visitor
            for z in current_zones:
                if z.id in entered_zones:
                    self._active_sessions[cam_id][vid][z.id] = frame.timestamp
                    # Timeline: Reached Checkout
                    if z.type.value == "checkout":
                        asyncio.create_task(timeline_service.log_event(
                            "Reached Checkout", cam_id, frame.timestamp, vid, {"zone_id": z.id}
                        ))

            # 1.5 Check for Queue Detected
            checkout_count = 0
            for v_id, z_dict in self._active_sessions[cam_id].items():
                for z_id in z_dict:
                    # Look up if z_id is checkout
                    z_info = next((zone for zone in zone_manager.get_zones(cam_id) if zone.id == z_id), None)
                    if z_info and z_info.type.value == "checkout":
                        checkout_count += 1
                        break
            
            if checkout_count >= 2:
                last_q = self._last_queue_time.get(cam_id, 0.0)
                if frame.timestamp - last_q > 30.0:  # 30 second cooldown
                    self._last_queue_time[cam_id] = frame.timestamp
                    asyncio.create_task(timeline_service.log_event(
                        "Queue Detected", cam_id, frame.timestamp, None, {"queue_size": checkout_count}
                    ))

            # 2. Zones exited
            exited_zone_ids = active_zones_for_visitor - current_zone_ids
            for zid in exited_zone_ids:
                entry_ts = self._active_sessions[cam_id][vid].pop(zid)
                duration = frame.timestamp - entry_ts
                if duration > 1.0:  # Skip micro-visits to filter noise
                    # Find zone_type (fetch from zone manager cache)
                    zone_type = "unknown"
                    for z in zone_manager.get_zones(cam_id):
                        if z.id == zid:
                            zone_type = z.type.value
                            break

                    asyncio.create_task(
                        self._save_zone_visit(
                            camera_id=cam_id,
                            visitor_id=vid,
                            zone_id=zid,
                            zone_type=zone_type,
                            entry_ts=entry_ts,
                            exit_ts=frame.timestamp,
                            duration=duration
                        ),
                        name=f"zone-analytics-{vid}-{zid}"
                    )
                    


    async def process_visitor_event(self, event: VisitorEvent) -> None:
        # If visitor track is removed (exit), close all open zone sessions for them
        if event.event_type == VisitorEventType.EXIT:
            cam_id = event.camera_id
            vid = event.visitor_id
            if cam_id in self._active_sessions and vid in self._active_sessions[cam_id]:
                open_zones = dict(self._active_sessions[cam_id][vid])
                for zid, entry_ts in open_zones.items():
                    duration = event.timestamp - entry_ts
                    if duration > 1.0:
                        zone_type = "unknown"
                        for z in zone_manager.get_zones(cam_id):
                            if z.id == zid:
                                zone_type = z.type.value
                                break

                        asyncio.create_task(
                            self._save_zone_visit(
                                camera_id=cam_id,
                                visitor_id=vid,
                                zone_id=zid,
                                zone_type=zone_type,
                                entry_ts=entry_ts,
                                exit_ts=event.timestamp,
                                duration=duration
                            )
                        )

                # Cleanup
                del self._active_sessions[cam_id][vid]

    async def _save_zone_visit(
        self,
        camera_id: str,
        visitor_id: int,
        zone_id: str,
        zone_type: str,
        entry_ts: float,
        exit_ts: float,
        duration: float
    ) -> None:
        try:
            async with AsyncSessionLocal() as session:
                await analytics_repository.save_zone_visit_record(
                    session=session,
                    camera_id=camera_id,
                    visitor_id=visitor_id,
                    zone_id=zone_id,
                    zone_type=zone_type,
                    entry_ts=entry_ts,
                    exit_ts=exit_ts,
                    duration_seconds=duration,
                )
                await session.commit()
        except Exception as exc:
            logger.error("Failed to save zone visit", extra={"error": str(exc), "visitor": visitor_id, "zone": zone_id})

    async def get_zone_analytics_report(
        self,
        camera_id: str,
        since_ts: float,
        until_ts: float | None = None,
    ) -> dict[str, Any]:
        """Fetch and calculate zone analytics for a camera."""
        async with AsyncSessionLocal() as session:
            records = await analytics_repository.get_zone_visit_records(
                session=session,
                camera_id=camera_id,
                since_ts=since_ts,
                until_ts=until_ts
            )
        active_zones = zone_manager.get_active_zones(camera_id)
        return calculate_zone_statistics(records, active_zones)

zone_analytics_service = ZoneAnalyticsService()
