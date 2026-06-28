import pytest
from app.db.timeline_repository import timeline_repository, TimelineEventModel
from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base

@pytest.mark.asyncio
async def test_timeline_repository_crud():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        # Create events
        await timeline_repository.create_event(
            session=session,
            event_type="Customer Entered",
            camera_id="cam_test",
            timestamp=100.0,
            visitor_id=1,
            details='{"confidence": 0.99}'
        )
        await timeline_repository.create_event(
            session=session,
            event_type="Reached Checkout",
            camera_id="cam_test",
            timestamp=150.0,
            visitor_id=1
        )
        await timeline_repository.create_event(
            session=session,
            event_type="Customer Entered",
            camera_id="cam_other",
            timestamp=120.0,
            visitor_id=2
        )
        await session.commit()
        
    async with AsyncSessionLocal() as session:
        # Get all
        events = await timeline_repository.get_events(session)
        assert len(events) >= 3
        
        # Filter by camera
        cam_events = await timeline_repository.get_events(session, camera_id="cam_test")
        assert len(cam_events) == 2
        
        # Filter by event type
        type_events = await timeline_repository.get_events(session, event_types=["Customer Entered"])
        assert len(type_events) == 2
        
        # Filter by time
        time_events = await timeline_repository.get_events(session, start_ts=110.0, end_ts=160.0)
        assert len(time_events) == 2  # 120 and 150
