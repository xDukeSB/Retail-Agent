"""
metrics.py — Prometheus Metrics Registry.

Defines global Prometheus metrics for RetailAI Agent.
"""

from prometheus_client import Gauge, Counter, Histogram

# ── Hardware & System ──────────────────────────────────────────────────────
system_cpu_usage = Gauge('retailai_system_cpu_usage_percent', 'CPU usage percentage')
system_memory_usage = Gauge('retailai_system_memory_usage_bytes', 'Memory usage in bytes')

# ── Inference Engine ───────────────────────────────────────────────────────
inference_fps = Gauge('retailai_inference_fps', 'Frames processed per second', ['camera_id'])
inference_latency_ms = Histogram(
    'retailai_inference_latency_ms', 
    'Latency of YOLO + ByteTrack processing', 
    ['camera_id'],
    buckets=(10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)
)
total_detections = Counter('retailai_total_detections', 'Total objects detected across all frames', ['camera_id', 'class_name'])

# ── Cameras ────────────────────────────────────────────────────────────────
camera_status = Gauge('retailai_camera_status', '1 if active, 0 if offline', ['camera_id'])
camera_reconnects = Counter('retailai_camera_reconnects_total', 'Number of times camera connection was lost', ['camera_id'])

# ── Offline-First Sync ─────────────────────────────────────────────────────
sync_queue_size = Gauge('retailai_sync_queue_size', 'Number of unsynced events in SQLite')
sync_success_count = Counter('retailai_sync_success_total', 'Number of successful cloud syncs')
sync_error_count = Counter('retailai_sync_errors_total', 'Number of failed cloud syncs')
