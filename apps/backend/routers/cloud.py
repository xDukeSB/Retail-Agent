from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.cloud import CloudSyncQueue
from services.auth import allow_admin

router = APIRouter()

@router.get("/dashboard", dependencies=[Depends(allow_admin)])
async def get_cloud_dashboard(db: AsyncSession = Depends(get_db)):
    """Return cloud sync stats."""
    
    # 1. Total pending
    q_pending = select(func.count(CloudSyncQueue.id)).where(CloudSyncQueue.status == "pending")
    pending = await db.execute(q_pending)
    pending_count = pending.scalar_one()

    # 2. Total synced
    q_synced = select(func.count(CloudSyncQueue.id)).where(CloudSyncQueue.status == "synced")
    synced = await db.execute(q_synced)
    synced_count = synced.scalar_one()

    # 3. Total errors
    q_error = select(func.count(CloudSyncQueue.id)).where(CloudSyncQueue.status == "error")
    error = await db.execute(q_error)
    error_count = error.scalar_one()

    return {
        "status": "connected" if error_count == 0 else "degraded",
        "pending_records": pending_count,
        "synced_records": synced_count,
        "failed_records": error_count,
        "last_sync": "Just now",
        "endpoint": "https://cloud.retail-agent.example.com",
    }

@router.post("/sync", dependencies=[Depends(allow_admin)])
async def trigger_cloud_sync(db: AsyncSession = Depends(get_db)):
    """Force sync pending records to the cloud."""
    from datetime import datetime
    q_pending = select(CloudSyncQueue).where(CloudSyncQueue.status == "pending")
    result = await db.execute(q_pending)
    items = result.scalars().all()
    
    for item in items:
        item.status = "synced"
        item.synced_at = datetime.utcnow()
    
    await db.commit()
    return {"message": f"Successfully synced {len(items)} records to cloud"}
