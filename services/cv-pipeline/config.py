"""CV Pipeline configuration."""
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class PipelineConfig:
    # Stream
    rtsp_url: str = ""
    stream_width: int = 1280
    stream_height: int = 720
    target_fps: int = 10  # Process at 10fps for efficiency

    # YOLO
    model_path: str = "./data/models/yolo11n.pt"
    confidence_threshold: float = 0.45
    device: str = "cpu"  # cpu | cuda | mps
    person_class_id: int = 0  # COCO class 0 = person

    # ByteTrack
    track_thresh: float = 0.5
    track_buffer: int = 30
    match_thresh: float = 0.8

    # Backend API
    backend_url: str = "http://localhost:8000"
    event_batch_size: int = 10
    heatmap_push_interval_seconds: int = 120

    # Heatmap grid
    heatmap_grid_size: int = 100

    # Zone event throttle (seconds between duplicate zone events)
    zone_event_throttle: float = 2.0


def load_camera_config(camera_id: str) -> PipelineConfig:
    """Load config from environment variables."""
    return PipelineConfig(
        rtsp_url=os.getenv("CAMERA_RTSP_URL", ""),
        model_path=os.getenv("YOLO_MODEL_PATH", "./data/models/yolo11n.pt"),
        confidence_threshold=float(os.getenv("YOLO_CONFIDENCE", "0.45")),
        device=os.getenv("YOLO_DEVICE", "cpu"),
        backend_url=os.getenv("BACKEND_URL", "http://localhost:8000"),
        target_fps=int(os.getenv("TARGET_FPS", "10")),
    )
