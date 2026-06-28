"""
RetailAI Agent — CV Pipeline
Orchestrates YOLOv11n + ByteTrack per camera.
Privacy-first: only person centroids are tracked, no faces, no biometrics.
"""
import argparse
import asyncio
import logging
import signal
import sys

from config import PipelineConfig, load_camera_config
from pipeline import CameraPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cv-pipeline")


async def run_pipeline(camera_id: str, config: PipelineConfig):
    pipeline = CameraPipeline(camera_id, config)

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await pipeline.run(stop_event)


def main():
    parser = argparse.ArgumentParser(description="RetailAI CV Pipeline")
    parser.add_argument("--camera-id", required=True, help="Camera ID from backend")
    parser.add_argument("--config", default=".env", help="Config file path")
    args = parser.parse_args()

    config = load_camera_config(args.camera_id)
    logger.info(f"Starting CV pipeline for camera: {args.camera_id}")
    asyncio.run(run_pipeline(args.camera_id, config))


if __name__ == "__main__":
    main()
