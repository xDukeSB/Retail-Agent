import pytest
import httpx
import asyncio
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.db.timeline_repository import timeline_repository
from app.services.sync_service import sync_service

@pytest.mark.asyncio
async def test_sync_service():
    # Setup DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError
        tables_to_migrate = [
            "timeline_events",
            "dwell_time_analytics",
            "zone_visit_analytics",
            "checkout_analytics",
            "crossing_events"
        ]
        for table in tables_to_migrate:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN synced BOOLEAN DEFAULT 0 NOT NULL"))
            except OperationalError:
                pass

    ts = datetime.now(timezone.utc).timestamp()

    async with AsyncSessionLocal() as session:
        # Create an unsynced event
        await timeline_repository.create_event(session, "Customer Entered", "cam_sync_test", ts)
        await session.commit()
    
    # Mock httpx.AsyncClient.head (for internet check) and post (for upload)
    with patch("httpx.AsyncClient.head", new_callable=AsyncMock) as mock_head:
        mock_head.return_value.status_code = 200
        
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            
            # Start sync service manually executing loop logic
            payload, models = await sync_service._gather_unsynced_payload()
            assert "timeline_events" in payload
            assert len(payload["timeline_events"]) >= 1
            
            await sync_service._mark_as_synced(models)
            
            # Verify it was synced
            payload2, models2 = await sync_service._gather_unsynced_payload()
            assert "timeline_events" not in payload2 or len(payload2.get("timeline_events", [])) == 0
