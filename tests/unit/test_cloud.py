import pytest
from app.services.cloud_service import cloud_service

@pytest.mark.asyncio
async def test_cloud_dashboard_data():
    data = await cloud_service.get_dashboard_data()
    
    assert "stores" in data
    assert "regions" in data
    assert "executive_summary" in data
    
    assert len(data["stores"]) == 5
    
    offline_stores = [s for s in data["stores"] if s["status"] == "Offline"]
    assert len(offline_stores) >= 1
    
    exec_summary = data["executive_summary"]
    assert exec_summary["active_alerts"] >= 1
    assert exec_summary["total_global_visitors"] > 0
