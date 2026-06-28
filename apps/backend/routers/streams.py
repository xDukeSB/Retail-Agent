"""Streams router — proxy stream health and HLS URLs for the frontend."""
from typing import List

import httpx
from fastapi import APIRouter

from config import settings

router = APIRouter()


@router.get("/")
async def list_streams():
    """
    Returns list of active streams from MediaMTX.
    Falls back gracefully if MediaMTX is not running.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                f"http://{settings.MEDIAMTX_HOST}:{settings.MEDIAMTX_API_PORT}/v3/paths/list"
            )
            data = resp.json()
            paths = data.get("items", [])
            return {
                "streams": [
                    {
                        "name": p.get("name"),
                        "rtsp_url": f"rtsp://{settings.MEDIAMTX_HOST}:{settings.MEDIAMTX_RTSP_PORT}/{p.get('name')}",
                        "hls_url": f"http://{settings.MEDIAMTX_HOST}:{settings.MEDIAMTX_HLS_PORT}/{p.get('name')}/index.m3u8",
                        "ready": p.get("ready", False),
                        "readers": p.get("readers", 0),
                    }
                    for p in paths
                ]
            }
    except Exception:
        return {"streams": [], "mediamtx_unavailable": True}


@router.get("/{camera_id}/hls-url")
async def get_hls_url(camera_id: str):
    """Return the HLS playback URL for a given camera."""
    return {
        "camera_id": camera_id,
        "hls_url": f"http://{settings.MEDIAMTX_HOST}:{settings.MEDIAMTX_HLS_PORT}/{camera_id}/index.m3u8",
        "rtsp_url": f"rtsp://{settings.MEDIAMTX_HOST}:{settings.MEDIAMTX_RTSP_PORT}/{camera_id}",
    }


@router.get("/{camera_id}/health")
async def stream_health(camera_id: str):
    """Check if a specific stream is live in MediaMTX."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                f"http://{settings.MEDIAMTX_HOST}:{settings.MEDIAMTX_API_PORT}/v3/paths/get/{camera_id}"
            )
            data = resp.json()
            return {
                "camera_id": camera_id,
                "live": data.get("ready", False),
                "source": data.get("source"),
            }
    except Exception:
        return {"camera_id": camera_id, "live": False, "error": "MediaMTX unavailable"}

from fastapi.responses import StreamingResponse
from services.cv_pipeline.engine_manager import engine_manager
import asyncio

@router.get("/{camera_id}/video_feed")
async def get_video_feed(camera_id: str):
    """Streams annotated MJPEG feed for a camera.
    
    Waits up to 10 seconds for the first frame before streaming,
    preventing premature browser onerror when the camera is initializing.
    Uses MJPEG multipart format which is natively supported by <img> tags.
    """
    async def generate_feed():
        # Wait for the first frame for up to 10 seconds
        waited = 0.0
        while waited < 10.0:
            frame_bytes = engine_manager.get_latest_frame(camera_id)
            if frame_bytes:
                break
            await asyncio.sleep(0.2)
            waited += 0.2

        # Streaming loop — runs until client disconnects
        while True:
            frame_bytes = engine_manager.get_latest_frame(camera_id)
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            # ~30 FPS cap — sleep prevents busy-looping
            await asyncio.sleep(0.033)

    return StreamingResponse(
        generate_feed(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }
    )
