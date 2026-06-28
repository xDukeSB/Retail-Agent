from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db
from models.store import Store
from services.auth import allow_admin, allow_manager, allow_viewer

router = APIRouter()

class SettingsUpdate(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    address: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    
    # Sync Toggles
    auto_sync: Optional[bool] = None
    sync_metadata: Optional[bool] = None
    sync_analytics: Optional[bool] = None
    sync_reports: Optional[bool] = None
    sync_video: Optional[bool] = None
    
    # Feature Toggles
    queue_detection: Optional[bool] = None
    transaction_detection: Optional[bool] = None
    heatmap_generation: Optional[bool] = None
    zone_tracking: Optional[bool] = None
    face_anonymization: Optional[bool] = None
    
    # AI Engine Settings
    detection_confidence: Optional[float] = None
    frame_evaluation_rate: Optional[int] = None


@router.get("", dependencies=[Depends(allow_viewer)])
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store))
    store = result.scalars().first()
    if not store:
        # Should not happen as we seed the store in main.py
        store = Store()
        db.add(store)
        await db.commit()
        await db.refresh(store)
    return store

@router.put("", dependencies=[Depends(allow_manager)])
async def update_settings(settings: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store))
    store = result.scalars().first()
    
    if not store:
        store = Store()
        db.add(store)
        
    update_data = settings.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(store, key, value)
        
    await db.commit()
    await db.refresh(store)
    return store
