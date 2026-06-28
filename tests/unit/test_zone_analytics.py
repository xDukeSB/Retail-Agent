import pytest
from app.db.analytics_repository import ZoneVisitAnalyticsModel
from app.services.zone_manager import Zone, ZoneType
from app.services.zone_analytics_calculator import calculate_zone_statistics

def test_calculate_zone_statistics_empty():
    active_zones = [
        Zone(id="z1", name="Entrance", type=ZoneType.ENTRANCE, camera_id="cam1", vertices=[]),
        Zone(id="z2", name="Snacks", type=ZoneType.SNACKS, camera_id="cam1", vertices=[])
    ]
    
    stats = calculate_zone_statistics([], active_zones)
    
    assert stats["total_zone_visits"] == 0
    assert "z1" in stats["zone_stats"]
    assert stats["zone_stats"]["z1"]["visits"] == 0
    
    assert len(stats["ignored_zones"]) == 2
    assert len(stats["popular_zones"]) == 0

def test_calculate_zone_statistics_multiple_visits():
    active_zones = [
        Zone(id="z1", name="Snacks", type=ZoneType.SNACKS, camera_id="cam1", vertices=[]),
        Zone(id="z2", name="Drinks", type=ZoneType.DRINKS, camera_id="cam1", vertices=[])
    ]
    
    records = [
        ZoneVisitAnalyticsModel(zone_id="z1", zone_type="snacks", duration_seconds=10.0),
        ZoneVisitAnalyticsModel(zone_id="z1", zone_type="snacks", duration_seconds=20.0),
        ZoneVisitAnalyticsModel(zone_id="z2", zone_type="drinks", duration_seconds=5.0)
    ]
    
    stats = calculate_zone_statistics(records, active_zones)
    
    assert stats["total_zone_visits"] == 3
    assert stats["zone_stats"]["z1"]["visits"] == 2
    assert stats["zone_stats"]["z1"]["average_duration"] == 15.0
    
    assert stats["zone_stats"]["z2"]["visits"] == 1
    assert stats["zone_stats"]["z2"]["average_duration"] == 5.0
    
    assert len(stats["popular_zones"]) == 2
    assert stats["popular_zones"][0]["zone_id"] == "z1"  # Snacks is most popular (2 visits vs 1)
    
    assert len(stats["ignored_zones"]) == 0

def test_calculate_zone_statistics_deleted_zone():
    active_zones = []
    
    records = [
        ZoneVisitAnalyticsModel(zone_id="deleted_z", zone_type="electronics", duration_seconds=10.0)
    ]
    
    stats = calculate_zone_statistics(records, active_zones)
    
    assert stats["total_zone_visits"] == 1
    assert stats["zone_stats"]["deleted_z"]["visits"] == 1
    assert "Deleted Zone" in stats["zone_stats"]["deleted_z"]["name"]
