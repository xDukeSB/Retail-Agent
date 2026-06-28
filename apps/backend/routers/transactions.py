from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from database import get_db
from models.transaction import Transaction, TransactionEvent
from services.auth import allow_viewer, allow_manager

router = APIRouter()

class TransactionCreate(BaseModel):
    store_id: Optional[str] = None
    amount: float
    timestamp: datetime
    source: str
    status: str = "completed"

class TransactionEventCreate(BaseModel):
    transaction_id: str
    track_id: Optional[str] = None
    timestamp: datetime

@router.post("/", dependencies=[Depends(allow_manager)])
async def create_transaction(txn: TransactionCreate, db: AsyncSession = Depends(get_db)):
    db_txn = Transaction(
        id=str(uuid.uuid4()),
        store_id=txn.store_id,
        amount=txn.amount,
        timestamp=txn.timestamp,
        source=txn.source,
        status=txn.status
    )
    db.add(db_txn)
    await db.commit()
    return {"id": db_txn.id, "status": "ok"}

@router.get("/", dependencies=[Depends(allow_viewer)])
async def get_transactions(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    q = select(Transaction).order_by(Transaction.timestamp.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()

@router.post("/events", dependencies=[Depends(allow_manager)])
async def create_transaction_event(event: TransactionEventCreate, db: AsyncSession = Depends(get_db)):
    db_event = TransactionEvent(
        id=str(uuid.uuid4()),
        transaction_id=event.transaction_id,
        track_id=event.track_id,
        timestamp=event.timestamp
    )
    db.add(db_event)
    await db.commit()
    return {"id": db_event.id, "status": "ok"}

@router.get("/events", dependencies=[Depends(allow_viewer)])
async def get_transaction_events(transaction_id: str, db: AsyncSession = Depends(get_db)):
    q = select(TransactionEvent).where(TransactionEvent.transaction_id == transaction_id)
    result = await db.execute(q)
    return result.scalars().all()
