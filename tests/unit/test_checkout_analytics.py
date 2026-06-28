import pytest
from datetime import datetime, timezone

from app.db.checkout_repository import checkout_repository
from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base

@pytest.mark.asyncio
async def test_checkout_repository():
    # Setup DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    ts = datetime.now(timezone.utc).timestamp()

    async with AsyncSessionLocal() as session:
        # Create a checkout session
        record = await checkout_repository.save_checkout_session(
            session=session,
            camera_id="cam_test",
            visitor_id=1,
            entry_ts=ts,
            exit_ts=ts + 12.0,
            duration_seconds=12.0,
            purchase_probability=0.66,
            confidence_score=0.95
        )
        await session.commit()
        
        assert record.id is not None
        
        metrics = await checkout_repository.get_metrics(session, camera_id="cam_test")
        assert metrics["total_checkout_visitors"] == 1
        assert metrics["average_purchase_probability"] == 0.66
        
        sessions = await checkout_repository.get_sessions(session, camera_id="cam_test")
        assert len(sessions) == 1
        assert sessions[0].visitor_id == 1
