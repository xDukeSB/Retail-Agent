"""
zone_analytics_calculator.py — Pure functions for calculating zone metrics.
"""
from __future__ import annotations

import statistics
from typing import Any, Sequence

from app.db.analytics_repository import ZoneVisitAnalyticsModel
from app.services.zone_manager import Zone


def calculate_zone_statistics(
    records: Sequence[ZoneVisitAnalyticsModel],
    active_zones: list[Zone]
) -> dict[str, Any]:
    """
    Computes zone metrics: visits, durations, popular, ignored.
    """
    zone_stats = {}
    for z in active_zones:
        zone_stats[z.id] = {
            "name": z.name,
            "type": z.type.value,
            "visits": 0,
            "durations": [],
            "average_duration": 0.0,
            "total_duration": 0.0
        }

    # If there are records for deleted zones, we still aggregate them under their ID
    # but they won't have a name/type predefined.
    for r in records:
        if r.zone_id not in zone_stats:
            zone_stats[r.zone_id] = {
                "name": f"Deleted Zone {r.zone_id[:6]}",
                "type": r.zone_type,
                "visits": 0,
                "durations": [],
                "average_duration": 0.0,
                "total_duration": 0.0
            }
        
        zone_stats[r.zone_id]["visits"] += 1
        zone_stats[r.zone_id]["durations"].append(r.duration_seconds)
        zone_stats[r.zone_id]["total_duration"] += r.duration_seconds

    # Finalize averages
    for zid, stats in zone_stats.items():
        if stats["durations"]:
            stats["average_duration"] = round(statistics.mean(stats["durations"]), 1)
        # remove raw array
        del stats["durations"]

    # Sort to find popular and ignored
    # We sort by visits descending, then by total_duration descending
    sorted_zones = sorted(
        zone_stats.items(),
        key=lambda item: (item[1]["visits"], item[1]["total_duration"]),
        reverse=True
    )

    popular_zones = [
        {"zone_id": zid, "name": stats["name"], "visits": stats["visits"]}
        for zid, stats in sorted_zones if stats["visits"] > 0
    ]

    ignored_zones = [
        {"zone_id": zid, "name": stats["name"]}
        for zid, stats in sorted_zones if stats["visits"] == 0
    ]

    return {
        "total_zone_visits": len(records),
        "zone_stats": zone_stats,
        "popular_zones": popular_zones,
        "ignored_zones": ignored_zones
    }
