"""
dwell_time_calculator.py — Math logic for calculating advanced dwell time stats.
"""
import statistics
from typing import Sequence, Dict, Any


def calculate_statistics(durations: Sequence[float]) -> Dict[str, Any]:
    """
    Calculate average, median, longest, and shortest durations.
    Returns None for the values if the list is empty.
    """
    if not durations:
        return {
            "average_dwell_time": None,
            "median_dwell_time": None,
            "longest_visit": None,
            "shortest_visit": None,
            "total_visits_analyzed": 0,
        }

    return {
        "average_dwell_time": round(statistics.mean(durations), 1),
        "median_dwell_time": round(statistics.median(durations), 1),
        "longest_visit": round(max(durations), 1),
        "shortest_visit": round(min(durations), 1),
        "total_visits_analyzed": len(durations),
    }
