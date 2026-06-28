import pytest
from datetime import datetime, timezone

from app.db.checkout_repository import checkout_repository
from app.db.timeline_repository import timeline_repository
from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.services.reporting_service import reporting_service

@pytest.mark.asyncio
async def test_reporting_aggregations():
    # Setup DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    ts = datetime.now(timezone.utc).timestamp()

    async with AsyncSessionLocal() as session:
        # Create some events
        await timeline_repository.create_event(session, "Customer Entered", "cam1", ts)
        await timeline_repository.create_event(session, "Customer Entered", "cam1", ts + 10)
        await timeline_repository.create_event(session, "Queue Detected", "cam1", ts + 1800)

        # Create checkout record
        await checkout_repository.save_checkout_session(
            session=session,
            camera_id="cam1",
            visitor_id=1,
            entry_ts=ts,
            exit_ts=ts + 12.0,
            duration_seconds=12.0,
            purchase_probability=0.8,
            confidence_score=0.9
        )
        await session.commit()
        
    # Generate Report Data
    data = await reporting_service.generate_report_data(timeframe="daily", days_back=7)
    assert len(data) >= 1
    
    # Check last row
    last_row = data[-1]
    assert last_row["Visitors"] >= 2
    assert last_row["Queue Events"] >= 1
    assert last_row["Conversion (%)"] > 0
    
    # Test CSV export
    csv_out = reporting_service.export_csv(data)
    assert "Date,Visitors" in csv_out
    
    # Test Excel export
    excel_out = reporting_service.export_excel(data)
    assert excel_out is not None
    assert len(excel_out) > 0
    
    # Test PDF export
    pdf_out = reporting_service.export_pdf(data)
    assert pdf_out is not None
    assert len(pdf_out) > 0
