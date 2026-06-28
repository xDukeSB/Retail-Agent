import asyncio
import logging
import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal
from models.cloud import CloudSyncQueue

logger = logging.getLogger("retailai.cloud")

class CloudSyncService:
    def __init__(self, endpoint: str = "https://cloud.retail-agent.example.com", interval_seconds: int = 30):
        self.endpoint = endpoint
        self.interval = interval_seconds
        self._running = False

    async def run_loop(self):
        self._running = True
        logger.info(f"🌩️ Cloud Sync Engine started (interval={self.interval}s)")
        
        while self._running:
            try:
                await self._process_queue()
            except Exception as e:
                logger.error(f"Cloud Sync error: {e}")
            
            await asyncio.sleep(self.interval)

    async def _process_queue(self):
        async with AsyncSessionLocal() as db:
            # Fetch pending items
            query = select(CloudSyncQueue).where(CloudSyncQueue.status == "pending").limit(100)
            result = await db.execute(query)
            items = result.scalars().all()

            if not items:
                return

            logger.info(f"Syncing {len(items)} records to cloud...")

            # In a real app we'd POST to self.endpoint.
            # Here we simulate success.
            await asyncio.sleep(0.5)

            for item in items:
                item.status = "synced"
                item.synced_at = datetime.utcnow()
            
            await db.commit()
            logger.info(f"✅ Synced {len(items)} records.")

def enqueue_sync(db: AsyncSession, table_name: str, record_id: str, payload: dict, action: str = "upsert"):
    """Helper to add records to the sync queue."""
    item = CloudSyncQueue(
        table_name=table_name,
        record_id=record_id,
        action=action,
        payload=json.dumps(payload),
        status="pending"
    )
    db.add(item)
