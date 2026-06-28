"""
sync_service.py — Offline-First Sync Engine.
Synchronizes unsynced database records to a cloud replica endpoint.
"""
from __future__ import annotations

import asyncio
import httpx
from typing import List, Dict, Any

from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.core.logging import get_logger

from app.db.timeline_repository import TimelineEventModel
from app.db.analytics_repository import DwellTimeAnalyticsModel, ZoneVisitAnalyticsModel
from app.db.checkout_repository import CheckoutAnalyticsModel
from app.db.event_repository import CrossingEventModel

logger = get_logger(__name__)

# Mock Cloud Endpoint
CLOUD_SYNC_URL = "https://httpbin.org/post"
# Cloud Ping URL to check connectivity
CLOUD_PING_URL = "https://1.1.1.1"

class SyncService:
    def __init__(self):
        self._running = False
        self._task = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info("Offline-First Sync Engine started.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Offline-First Sync Engine stopped.")

    async def _check_internet(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.head(CLOUD_PING_URL)
                return resp.status_code >= 200
        except httpx.RequestError:
            return False

    async def _sync_loop(self):
        backoff_delay = 30.0
        max_delay = 300.0
        
        while self._running:
            await asyncio.sleep(backoff_delay)
            
            # 1. Check internet connectivity
            if not await self._check_internet():
                logger.warning(f"Sync Service: Offline. Deferring sync. Next check in {backoff_delay}s.")
                backoff_delay = min(backoff_delay * 1.5, max_delay)
                continue
                
            # Reset backoff on success
            backoff_delay = 30.0
                
            # 2. Fetch unsynced records
            try:
                payload, models_to_update = await self._gather_unsynced_payload()
            except Exception as e:
                logger.error(f"Sync Service: Failed to gather data: {e}")
                continue

            if not any(payload.values()):
                # Nothing to sync
                continue

            # 3. Post to cloud
            try:
                logger.info(f"Sync Service: Uploading {sum(len(v) for v in payload.values())} records to cloud...")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(CLOUD_SYNC_URL, json=payload)
                    resp.raise_for_status()
            except Exception as e:
                logger.error(f"Sync Service: Upload failed: {e}. Retrying next cycle.")
                continue
                
            # 4. Mark as synced
            try:
                await self._mark_as_synced(models_to_update)
                logger.info("Sync Service: Synchronization complete.")
            except Exception as e:
                logger.error(f"Sync Service: Failed to update local DB after sync: {e}")

    async def _gather_unsynced_payload(self) -> tuple[Dict[str, List[Any]], Dict[Any, List[str]]]:
        payload = {}
        models_to_update = {}
        
        async with AsyncSessionLocal() as session:
            # Timeline Events
            stmt = select(TimelineEventModel).where(TimelineEventModel.synced == False).limit(500)
            result = await session.execute(stmt)
            tl_records = result.scalars().all()
            if tl_records:
                payload["timeline_events"] = [{"id": r.id, "type": r.event_type} for r in tl_records]
                models_to_update[TimelineEventModel] = [r.id for r in tl_records]

            # Dwell Time
            stmt = select(DwellTimeAnalyticsModel).where(DwellTimeAnalyticsModel.synced == False).limit(500)
            result = await session.execute(stmt)
            dwell_records = result.scalars().all()
            if dwell_records:
                payload["dwell_time"] = [r.to_dict() for r in dwell_records]
                models_to_update[DwellTimeAnalyticsModel] = [r.id for r in dwell_records]

            # Zone Visits
            stmt = select(ZoneVisitAnalyticsModel).where(ZoneVisitAnalyticsModel.synced == False).limit(500)
            result = await session.execute(stmt)
            zone_records = result.scalars().all()
            if zone_records:
                payload["zone_visits"] = [r.to_dict() for r in zone_records]
                models_to_update[ZoneVisitAnalyticsModel] = [r.id for r in zone_records]

            # Checkout Analytics
            stmt = select(CheckoutAnalyticsModel).where(CheckoutAnalyticsModel.synced == False).limit(500)
            result = await session.execute(stmt)
            co_records = result.scalars().all()
            if co_records:
                payload["checkout"] = [r.to_dict() for r in co_records]
                models_to_update[CheckoutAnalyticsModel] = [r.id for r in co_records]

            # Crossing Events
            stmt = select(CrossingEventModel).where(CrossingEventModel.synced == False).limit(500)
            result = await session.execute(stmt)
            cr_records = result.scalars().all()
            if cr_records:
                payload["crossings"] = [{"id": r.id, "type": r.event_type} for r in cr_records]
                models_to_update[CrossingEventModel] = [r.id for r in cr_records]

        return payload, models_to_update

    async def _mark_as_synced(self, models_to_update: Dict[Any, List[str]]):
        async with AsyncSessionLocal() as session:
            for model_cls, record_ids in models_to_update.items():
                if record_ids:
                    stmt = update(model_cls).where(model_cls.id.in_(record_ids)).values(synced=True)
                    await session.execute(stmt)
            await session.commit()

sync_service = SyncService()
