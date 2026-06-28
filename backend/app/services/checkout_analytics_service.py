"""
checkout_analytics_service.py — Dedicated service for tracking purchase probability in checkout zones.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.db.checkout_repository import checkout_repository
from app.db.session import AsyncSessionLocal
from app.services.tracking_models import TrackingFrame, VisitorEvent, VisitorEventType
from app.services.zone_manager import zone_manager
from app.services.timeline_service import timeline_service

logger = get_logger(__name__)

class CheckoutAnalyticsService:
    def __init__(self):
        # State: camera_id -> visitor_id -> dict of data
        self._active_sessions: dict[str, dict[int, dict[str, Any]]] = {}

    async def start(self, tracking_pipeline) -> None:
        tracking_pipeline.add_tracking_callback(self.process_tracking_frame)
        tracking_pipeline.add_event_callback(self.process_visitor_event)
        logger.info("CheckoutAnalyticsService started")

    async def stop(self, tracking_pipeline) -> None:
        tracking_pipeline.remove_tracking_callback(self.process_tracking_frame)
        tracking_pipeline.remove_event_callback(self.process_visitor_event)
        logger.info("CheckoutAnalyticsService stopped")

    def _calculate_purchase_probability(self, duration_seconds: float) -> float:
        """Phase 1 heuristic for purchase probability."""
        if duration_seconds < 5.0:
            return 0.10
        elif duration_seconds <= 15.0:
            # Linear scaling from 10% to 90%
            return 0.10 + ((duration_seconds - 5.0) / 10.0) * 0.80
        else:
            return 0.90

    async def process_tracking_frame(self, frame: TrackingFrame) -> None:
        cam_id = frame.camera_id
        if cam_id not in self._active_sessions:
            self._active_sessions[cam_id] = {}

        for visitor in frame.tracked:
            vid = visitor.visitor_id
            
            # Check if visitor is in checkout zone
            in_checkout = False
            if visitor.position:
                zones = zone_manager.get_zones_for_point(
                    cam_id, visitor.position.x_norm, visitor.position.y_norm
                )
                for z in zones:
                    if z.type.value == "checkout":
                        in_checkout = True
                        break

            # Handle state
            if in_checkout:
                if vid not in self._active_sessions[cam_id]:
                    # Visitor enters checkout zone
                    self._active_sessions[cam_id][vid] = {
                        "entry_ts": frame.timestamp,
                        "last_seen_ts": frame.timestamp,
                        "cumulative_duration": 0.0,
                        "in_checkout": True,
                        "confidence_score": visitor.confidence
                    }
                else:
                    # Visitor remains in checkout zone
                    session = self._active_sessions[cam_id][vid]
                    if not session["in_checkout"]:
                        # Re-entered
                        session["in_checkout"] = True
                        session["last_seen_ts"] = frame.timestamp
                    else:
                        dt = frame.timestamp - session["last_seen_ts"]
                        session["cumulative_duration"] += dt
                        session["last_seen_ts"] = frame.timestamp
                    
                    # Update average confidence score smoothly
                    session["confidence_score"] = (session["confidence_score"] * 0.9) + (visitor.confidence * 0.1)
            else:
                if vid in self._active_sessions[cam_id]:
                    session = self._active_sessions[cam_id][vid]
                    if session["in_checkout"]:
                        # Visitor left checkout zone but might still be in store
                        session["in_checkout"] = False
                        dt = frame.timestamp - session["last_seen_ts"]
                        session["cumulative_duration"] += dt
                        session["last_seen_ts"] = frame.timestamp

    async def process_visitor_event(self, event: VisitorEvent) -> None:
        # If visitor track is removed (exit), close checkout session
        if event.event_type == VisitorEventType.EXIT:
            cam_id = event.camera_id
            vid = event.visitor_id
            if cam_id in self._active_sessions and vid in self._active_sessions[cam_id]:
                session = self._active_sessions[cam_id][vid]
                
                # Finalize duration
                if session["in_checkout"]:
                    dt = event.timestamp - session["last_seen_ts"]
                    session["cumulative_duration"] += dt
                
                duration = session["cumulative_duration"]
                entry_ts = session["entry_ts"]
                confidence = session["confidence_score"]
                
                # Minimum duration to be considered a valid checkout interaction
                if duration >= 1.0:
                    prob = self._calculate_purchase_probability(duration)
                    
                    # Store analytics record
                    asyncio.create_task(
                        self._save_checkout_session(
                            camera_id=cam_id,
                            visitor_id=vid,
                            entry_ts=entry_ts,
                            exit_ts=event.timestamp,
                            duration_seconds=duration,
                            purchase_probability=prob,
                            confidence_score=confidence
                        ),
                        name=f"checkout-analytics-{vid}"
                    )
                    
                    # Timeline: Likely Purchase (Only emit if prob is reasonably high)
                    if prob >= 0.50:
                        asyncio.create_task(timeline_service.log_event(
                            "Likely Purchase", 
                            cam_id, 
                            event.timestamp, 
                            vid, 
                            {
                                "duration": round(duration, 1),
                                "purchase_probability": round(prob, 2),
                                "confidence": round(confidence, 2)
                            }
                        ))
                        
                del self._active_sessions[cam_id][vid]

    async def _save_checkout_session(
        self,
        camera_id: str,
        visitor_id: int,
        entry_ts: float,
        exit_ts: float,
        duration_seconds: float,
        purchase_probability: float,
        confidence_score: float
    ) -> None:
        try:
            async with AsyncSessionLocal() as session:
                await checkout_repository.save_checkout_session(
                    session,
                    camera_id,
                    visitor_id,
                    entry_ts,
                    exit_ts,
                    duration_seconds,
                    purchase_probability,
                    confidence_score
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save checkout session: {e}", exc_info=True)

checkout_analytics_service = CheckoutAnalyticsService()
