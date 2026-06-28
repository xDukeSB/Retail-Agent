import pytest
from app.services.dwell_time_calculator import calculate_statistics

def test_calculate_statistics_empty():
    stats = calculate_statistics([])
    assert stats["average_dwell_time"] is None
    assert stats["median_dwell_time"] is None
    assert stats["longest_visit"] is None
    assert stats["shortest_visit"] is None
    assert stats["total_visits_analyzed"] == 0

def test_calculate_statistics_single():
    stats = calculate_statistics([15.0])
    assert stats["average_dwell_time"] == 15.0
    assert stats["median_dwell_time"] == 15.0
    assert stats["longest_visit"] == 15.0
    assert stats["shortest_visit"] == 15.0
    assert stats["total_visits_analyzed"] == 1

def test_calculate_statistics_multiple():
    durations = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = calculate_statistics(durations)
    assert stats["average_dwell_time"] == 30.0
    assert stats["median_dwell_time"] == 30.0
    assert stats["longest_visit"] == 50.0
    assert stats["shortest_visit"] == 10.0
    assert stats["total_visits_analyzed"] == 5

def test_calculate_statistics_even_count():
    durations = [10.0, 20.0, 30.0, 40.0]
    stats = calculate_statistics(durations)
    assert stats["average_dwell_time"] == 25.0
    assert stats["median_dwell_time"] == 25.0
    assert stats["longest_visit"] == 40.0
    assert stats["shortest_visit"] == 10.0
    assert stats["total_visits_analyzed"] == 4
