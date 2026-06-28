import pytest
from datetime import datetime, timezone, timedelta
from app.db.timeline_repository import timeline_repository
from app.db.analytics_repository import analytics_repository
from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.services.dashboard_service import dashboard_service

@pytest.mark.asyncio
async def test_dashboard_service_aggregations():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    now = datetime.now(timezone.utc)
    ts = now.replace(hour=10, minute=0, second=0).timestamp()

    async with AsyncSessionLocal() as session:
        # Create Timeline Events
        await timeline_repository.create_event(session, "Customer Entered", "cam1", ts)
        await timeline_repository.create_event(session, "Customer Entered", "cam1", ts + 10)
        await timeline_repository.create_event(session, "Customer Exited", "cam1", ts + 3600)
        await timeline_repository.create_event(session, "Likely Purchase", "cam1", ts + 3500)
        await timeline_repository.create_event(session, "Queue Detected", "cam1", ts + 1800)

        # Create Dwell Time
        await analytics_repository.save_dwell_time_record(
            session=session,
            camera_id="cam1",
            visitor_id=1,
            entry_ts=ts,
            exit_ts=ts + 3600,
            duration_seconds=3600
        )
        await session.commit()
        
    # Test Summary
    summary = await dashboard_service.get_summary()
    assert summary["total_entries"] >= 2
    assert summary["total_exits"] >= 1
    
    # Test Hourly Traffic
    hourly = await dashboard_service.get_hourly_traffic()
    assert len(hourly) == 24
    
    # Test Daily Traffic
    daily = await dashboard_service.get_daily_traffic(7)
    assert len(daily) > 0
    
    # Test Conversion
    conv = await dashboard_service.get_conversion_metrics()
    assert conv["likely_purchases"] >= 1
    assert conv["conversion_rate_pct"] > 0
    
    # Test Queue
    q = await dashboard_service.get_queue_metrics()
    assert q["total_queue_events"] >= 1
