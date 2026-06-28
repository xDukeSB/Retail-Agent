"""
cloud_service.py — Mock Multi-Store Central Cloud Aggregator.
Simulates a cloud platform receiving syncs from multiple edge stores.
"""
from __future__ import annotations

import time
import random
from typing import Any, Dict

class CloudService:
    def __init__(self):
        # We simulate the exact time to make "Last Sync" realistic.
        self._boot_time = time.time()

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Generate mock multi-store and regional data."""
        now = time.time()
        
        # Simulated Stores
        stores = [
            {
                "id": "st-1",
                "name": "Flagship (Local)",
                "region": "North America",
                "status": "Online",
                "last_sync": now - 15, # 15 seconds ago
                "last_heartbeat": now - 5,
                "metrics": {
                    "visitors_today": 1245,
                    "conversion_rate": 22.4,
                    "avg_dwell_seconds": 320,
                    "queue_events": 4
                }
            },
            {
                "id": "st-2",
                "name": "NYC Outlet",
                "region": "North America",
                "status": "Online",
                "last_sync": now - 45, # 45 seconds ago
                "last_heartbeat": now - 10,
                "metrics": {
                    "visitors_today": 3400,
                    "conversion_rate": 18.2,
                    "avg_dwell_seconds": 210,
                    "queue_events": 12
                }
            },
            {
                "id": "st-3",
                "name": "London Center",
                "region": "Europe",
                "status": "Online",
                "last_sync": now - 120, # 2 mins ago
                "last_heartbeat": now - 30,
                "metrics": {
                    "visitors_today": 890,
                    "conversion_rate": 25.1,
                    "avg_dwell_seconds": 450,
                    "queue_events": 2
                }
            },
            {
                "id": "st-4",
                "name": "Paris Branch",
                "region": "Europe",
                "status": "Offline",
                "last_sync": now - (7 * 3600) - (15 * 60), # 7 hours 15 mins ago
                "last_heartbeat": now - (7 * 3600), # 7 hours ago
                "metrics": {
                    "visitors_today": 210,  # Stale data
                    "conversion_rate": 15.0,
                    "avg_dwell_seconds": 180,
                    "queue_events": 0
                }
            },
            {
                "id": "st-5",
                "name": "Tokyo Station",
                "region": "Asia",
                "status": "Online",
                "last_sync": now - 18,
                "last_heartbeat": now - 5,
                "metrics": {
                    "visitors_today": 4500,
                    "conversion_rate": 30.5,
                    "avg_dwell_seconds": 150,
                    "queue_events": 20
                }
            }
        ]

        # Regional Aggregation
        regions = {}
        for s in stores:
            r = s["region"]
            if r not in regions:
                regions[r] = {
                    "region": r,
                    "total_visitors": 0,
                    "online_stores": 0,
                    "total_stores": 0,
                    "avg_conversion": 0.0
                }
            
            regions[r]["total_stores"] += 1
            regions[r]["total_visitors"] += s["metrics"]["visitors_today"]
            if s["status"] == "Online":
                regions[r]["online_stores"] += 1
                
        # Calculate true avg conversion across region
        for r in regions.values():
            reg_stores = [s for s in stores if s["region"] == r["region"]]
            if reg_stores:
                r["avg_conversion"] = round(sum(s["metrics"]["conversion_rate"] for s in reg_stores) / len(reg_stores), 1)

        # Format timestamps to ISO for frontend date-fns
        from datetime import datetime, timezone
        for s in stores:
            s["last_sync_iso"] = datetime.fromtimestamp(s["last_sync"], tz=timezone.utc).isoformat()
            s["last_heartbeat_iso"] = datetime.fromtimestamp(s["last_heartbeat"], tz=timezone.utc).isoformat()

        return {
            "stores": stores,
            "regions": list(regions.values()),
            "executive_summary": {
                "total_global_visitors": sum(s["metrics"]["visitors_today"] for s in stores),
                "global_conversion_rate": round(sum(s["metrics"]["conversion_rate"] for s in stores) / len(stores), 1),
                "active_alerts": len([s for s in stores if s["status"] == "Offline"]),
                "system_health": round(len([s for s in stores if s["status"] == "Online"]) / len(stores) * 100)
            }
        }

cloud_service = CloudService()
