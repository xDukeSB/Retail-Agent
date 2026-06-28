"""
Demo seed script — populates the local SQLite DB with realistic sample data.
Run: python scripts/seed-demo.py
"""
import asyncio
import uuid
import random
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from database import init_db, AsyncSessionLocal
from models.camera import Camera
from models.track import PersonTrack
from models.analytics import HourlyCount, HeatmapCell, DailyReport, QueueSnapshot
from models.event import ZoneEvent


def rand_time(base_date: date, hour: int) -> datetime:
    return datetime.combine(base_date, datetime.min.time()).replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
    )


async def seed():
    print("🌱 Seeding RetailAI Agent demo data...")
    await init_db()

    async with AsyncSessionLocal() as db:
        # ── Camera ─────────────────────────────────────
        cam_id = str(uuid.uuid4())
        cam2_id = str(uuid.uuid4())

        for cam in [
            Camera(
                id=cam_id,
                name="Entrance Camera",
                rtsp_url="rtsp://192.168.1.100:554/stream1",
                location="Front Door",
                status="active",
                zone_config='{"zones":[{"name":"Entry","type":"line","zone_type":"entry","color":"#10b981","points":[{"x":0.1,"y":0.5},{"x":0.4,"y":0.5}]},{"name":"Exit","type":"line","zone_type":"exit","color":"#f43f5e","points":[{"x":0.6,"y":0.5},{"x":0.9,"y":0.5}]}]}',
            ),
            Camera(
                id=cam2_id,
                name="Checkout Camera",
                rtsp_url="rtsp://192.168.1.101:554/stream1",
                location="Checkout Area",
                status="active",
                zone_config='{"zones":[{"name":"Queue Zone","type":"polygon","zone_type":"queue","color":"#f59e0b","points":[{"x":0.2,"y":0.2},{"x":0.8,"y":0.2},{"x":0.8,"y":0.8},{"x":0.2,"y":0.8}]},{"name":"Checkout","type":"polygon","zone_type":"checkout","color":"#3b82f6","points":[{"x":0.3,"y":0.3},{"x":0.7,"y":0.3},{"x":0.7,"y":0.7},{"x":0.3,"y":0.7}]}]}',
            ),
        ]:
            db.add(cam)

        # ── Daily data for last 30 days ─────────────────
        today = date.today()
        for d in range(30):
            target_date = today - timedelta(days=d)
            is_weekend = target_date.weekday() >= 5
            base_traffic = random.randint(180, 280) if is_weekend else random.randint(80, 160)

            # Hourly counts
            for hour in range(9, 21):  # 9am-9pm
                # Peak hours: 11-13 and 17-19
                peak_mult = 1.8 if hour in (11, 12, 13, 17, 18) else 1.0
                entries = int(random.randint(3, 20) * peak_mult)
                exits   = int(entries * random.uniform(0.7, 1.0))
                db.add(HourlyCount(
                    id=str(uuid.uuid4()),
                    camera_id=cam_id,
                    hour=datetime.combine(target_date, datetime.min.time()).replace(hour=hour),
                    entries=entries,
                    exits=exits,
                    peak_count=random.randint(entries, entries + 8),
                    total_tracks=entries,
                    avg_dwell_seconds=random.uniform(120, 480),
                    max_dwell_seconds=random.uniform(600, 1800),
                    computed_at=datetime.utcnow(),
                ))

            # Person tracks (sample, not full dataset for perf)
            for _ in range(min(base_traffic // 3, 20)):
                entry_hour = random.randint(9, 20)
                entry_dt   = rand_time(target_date, entry_hour)
                dwell      = random.uniform(60, 900)
                exit_dt    = entry_dt + timedelta(seconds=dwell)
                db.add(PersonTrack(
                    id=str(uuid.uuid4()),
                    camera_id=cam_id,
                    session_track_id=random.randint(1, 9999),
                    entry_time=entry_dt,
                    exit_time=exit_dt,
                    dwell_seconds=dwell,
                    zones_visited='["Entry","General"]',
                    date=target_date,
                    is_complete=True,
                ))

            # Daily report
            db.add(DailyReport(
                id=str(uuid.uuid4()),
                camera_id=cam_id,
                date=target_date,
                total_entries=base_traffic,
                total_exits=int(base_traffic * 0.92),
                unique_visitors=base_traffic,
                avg_dwell_seconds=random.uniform(150, 420),
                peak_hour=random.choice([11, 12, 13, 17, 18]),
                peak_count=random.randint(12, 35),
                conversion_rate=random.uniform(8.0, 22.0),
                computed_at=datetime.utcnow(),
            ))
            # Store-wide daily report (camera_id=None)
            db.add(DailyReport(
                id=str(uuid.uuid4()),
                camera_id=None,
                date=target_date,
                total_entries=base_traffic + random.randint(20, 60),
                total_exits=int(base_traffic * 0.90),
                unique_visitors=base_traffic + random.randint(10, 40),
                avg_dwell_seconds=random.uniform(150, 420),
                peak_hour=random.choice([11, 12, 17, 18]),
                peak_count=random.randint(15, 45),
                conversion_rate=random.uniform(8.0, 22.0),
                computed_at=datetime.utcnow(),
            ))

        # ── Heatmap (today) ────────────────────────────────
        for cy in range(100):
            for cx in range(100):
                # Simulate high density in center, lower at edges
                dist = ((cx - 50) ** 2 + (cy - 50) ** 2) ** 0.5
                base = max(0, 50 - dist)
                density = base * random.uniform(0.5, 1.5) + random.uniform(0, 5)
                if density > 2:
                    db.add(HeatmapCell(
                        id=str(uuid.uuid4()),
                        camera_id=cam_id,
                        date=today,
                        cell_x=cx,
                        cell_y=cy,
                        density=density,
                        visit_count=int(density / 3),
                        updated_at=datetime.utcnow(),
                    ))

        # ── Queue snapshots (today) ────────────────────────
        for hour in range(9, 21):
            for minute in [0, 15, 30, 45]:
                ts = datetime.combine(today, datetime.min.time()).replace(hour=hour, minute=minute)
                peak_mult = 2.0 if hour in (12, 13, 17, 18) else 1.0
                depth = max(0, int(random.gauss(3, 2) * peak_mult))
                db.add(QueueSnapshot(
                    id=str(uuid.uuid4()),
                    camera_id=cam2_id,
                    zone_name="Queue Zone",
                    timestamp=ts,
                    queue_depth=depth,
                    avg_wait_seconds=depth * random.uniform(15, 45),
                    max_wait_seconds=depth * random.uniform(30, 90),
                ))

        await db.commit()
        print(f"✅ Demo data seeded successfully!")
        print(f"   Camera 1: {cam_id[:8]}… (Entrance Camera)")
        print(f"   Camera 2: {cam2_id[:8]}… (Checkout Camera)")
        print(f"   30 days of daily reports, hourly counts, heatmap, queue snapshots")
        print(f"\n🚀 Start the backend: cd apps/backend && uvicorn main:app --reload")
        print(f"🚀 Start the frontend: cd apps/frontend && npm run dev")
        print(f"🌐 Open: http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(seed())
