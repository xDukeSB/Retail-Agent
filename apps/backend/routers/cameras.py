"""Camera management router — CRUD for camera configuration and zone setup."""
import json
import uuid
from datetime import datetime
from typing import List, Optional, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from database import get_db
from models.camera import Camera
from services.cv_pipeline.engine_manager import engine_manager

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ZonePoint(BaseModel):
    x: float
    y: float

class Zone(BaseModel):
    name: str
    type: str = "polygon"
    zone_type: str = "general"
    color: str = "#3b82f6"
    points: List[ZonePoint]

class ZoneConfig(BaseModel):
    zones: List[Zone] = []

class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    rtsp_url: str = Field(..., min_length=1)
    description: Optional[str] = None
    location: Optional[str] = None
    zone_config: Optional[ZoneConfig] = None
    username: Optional[str] = None
    password: Optional[str] = None
    fps_target: int = 10
    is_enabled: bool = True

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    is_enabled: Optional[bool] = None
    zone_config: Optional[ZoneConfig] = None
    fps_target: Optional[int] = None

class CameraResponse(BaseModel):
    id: str
    name: str
    rtsp_url: str
    description: Optional[str]
    location: Optional[str]
    status: str
    is_enabled: bool
    zone_config: Optional[Any]
    stream_config: Optional[Any]
    created_at: datetime
    updated_at: datetime
    # Fields expected by the frontend CameraRecord interface
    fps_target: int = 10
    avg_fps: Optional[float] = None
    health_score: Optional[float] = None
    last_seen_at: Optional[datetime] = None
    reconnect_count: int = 0
    last_error: Optional[str] = None
    is_active: bool = False
    has_credentials: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_camera(cls, cam: Camera) -> "CameraResponse":
        zone = None
        if cam.zone_config:
            try:
                zone = json.loads(cam.zone_config)
            except Exception:
                zone = None
        stream = None
        if cam.stream_config:
            try:
                stream = json.loads(cam.stream_config)
            except Exception:
                stream = None
        return cls(
            id=cam.id,
            name=cam.name,
            rtsp_url=cam.rtsp_url,
            description=cam.description,
            location=cam.location,
            status=cam.status,
            is_enabled=cam.is_enabled,
            zone_config=zone,
            stream_config=stream,
            created_at=cam.created_at,
            updated_at=cam.updated_at,
            is_active=cam.status == "active",
        )

class ValidateUrlRequest(BaseModel):
    url: str

class TestConnectionRequest(BaseModel):
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    timeout: int = 8


# ── Utility endpoints (must come BEFORE /{camera_id} to avoid route conflict) ──

@router.get("/stats")
async def get_camera_stats(db: AsyncSession = Depends(get_db)):
    """Returns summary stats for the camera management page header."""
    result = await db.execute(select(Camera))
    cameras = result.scalars().all()
    total = len(cameras)
    active = sum(1 for c in cameras if c.status == "active")
    degraded = sum(1 for c in cameras if c.status == "degraded")
    error = sum(1 for c in cameras if c.status == "error")
    return {"total": total, "active": active, "degraded": degraded, "error": error}

@router.get("/health/all")
async def get_all_health(db: AsyncSession = Depends(get_db)):
    """Returns health info for all cameras."""
    result = await db.execute(select(Camera))
    cameras = result.scalars().all()
    return [{"camera_id": c.id, "status": c.status, "health_score": None} for c in cameras]

@router.post("/validate-url")
async def validate_url(payload: ValidateUrlRequest):
    """Validates that a URL looks like a valid RTSP stream URL."""
    url = payload.url.strip()
    valid = url.startswith("rtsp://") or url.startswith("rtsps://")
    return {"valid": valid, "url": url}

@router.post("/test-connection")
async def test_connection(payload: TestConnectionRequest):
    """Attempts to test camera stream connectivity (simulated without opencv for speed)."""
    # Lightweight reachability check using httpx
    try:
        host_part = payload.url.replace("rtsp://", "").replace("rtsps://", "").split("/")[0]
        host = host_part.split(":")[0]
        port_str = host_part.split(":")[1] if ":" in host_part else "554"
        port = int(port_str)
        import socket, asyncio
        loop = asyncio.get_event_loop()
        def _check():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(payload.timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        reachable = await loop.run_in_executor(None, _check)
        return {"reachable": reachable, "host": host, "port": port}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


# ── CRUD Endpoints ────────────────────────────────────────────────────────────

@router.get("/", response_model=None)
async def list_cameras(
    status: Optional[str] = Query(None),
    include_inactive: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """List all cameras with summary stats (matches frontend getCameras())."""
    q = select(Camera).order_by(Camera.created_at)
    if not include_inactive:
        q = q.where(Camera.is_enabled == True)
    if status:
        q = q.where(Camera.status == status)
    result = await db.execute(q)
    cameras_list = result.scalars().all()

    # Also compute summary so frontend header works
    all_result = await db.execute(select(Camera))
    all_cams = all_result.scalars().all()
    summary = {
        "total": len(all_cams),
        "active": sum(1 for c in all_cams if c.status == "active"),
        "degraded": sum(1 for c in all_cams if c.status == "degraded"),
        "error": sum(1 for c in all_cams if c.status == "error"),
    }
    return {
        "cameras": [CameraResponse.from_orm_camera(c) for c in cameras_list],
        "summary": summary,
    }


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(payload: CameraCreate, db: AsyncSession = Depends(get_db)):
    initial_status = "connecting" if payload.is_enabled else "inactive"
    cam = Camera(
        id=str(uuid.uuid4()),
        name=payload.name,
        rtsp_url=payload.rtsp_url,
        description=payload.description,
        location=payload.location,
        status=initial_status,
        is_enabled=payload.is_enabled,
        zone_config=payload.zone_config.model_dump_json() if payload.zone_config else None,
    )
    db.add(cam)
    await db.flush()
    await db.refresh(cam)

    # Bug 4 Fix: auto-start CV pipeline worker if camera is enabled on creation
    if payload.is_enabled:
        engine_manager.add_camera(cam.id, cam.rtsp_url)

    return CameraResponse.from_orm_camera(cam)


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return CameraResponse.from_orm_camera(cam)


@router.get("/{camera_id}/health")
async def get_camera_health(camera_id: str, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"camera_id": camera_id, "status": cam.status, "health_score": None}




@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str, payload: CameraUpdate, db: AsyncSession = Depends(get_db)
):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    if payload.name is not None:
        cam.name = payload.name
    if payload.rtsp_url is not None:
        cam.rtsp_url = payload.rtsp_url
    if payload.description is not None:
        cam.description = payload.description
    if payload.location is not None:
        cam.location = payload.location
    if payload.is_enabled is not None:
        cam.is_enabled = payload.is_enabled
    if payload.zone_config is not None:
        cam.zone_config = payload.zone_config.model_dump_json()
    cam.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(cam)
    return CameraResponse.from_orm_camera(cam)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    engine_manager.remove_camera(camera_id)
    await db.delete(cam)


@router.put("/{camera_id}/zones", response_model=CameraResponse)
async def update_zones(
    camera_id: str, zone_config: ZoneConfig, db: AsyncSession = Depends(get_db)
):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.zone_config = zone_config.model_dump_json()
    cam.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(cam)
    return CameraResponse.from_orm_camera(cam)


@router.post("/{camera_id}/enable", response_model=CameraResponse)
async def enable_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.is_enabled = True
    cam.status = "connecting"
    cam.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(cam)
    engine_manager.add_camera(camera_id, cam.rtsp_url)
    return CameraResponse.from_orm_camera(cam)


@router.post("/{camera_id}/disable", response_model=CameraResponse)
async def disable_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.is_enabled = False
    cam.status = "inactive"
    cam.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(cam)
    engine_manager.remove_camera(camera_id)
    return CameraResponse.from_orm_camera(cam)


@router.post("/{camera_id}/restart")
async def restart_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.status = "connecting"
    cam.updated_at = datetime.utcnow()
    await db.flush()
    engine_manager.remove_camera(camera_id)
    engine_manager.add_camera(camera_id, cam.rtsp_url)
    return {"camera_id": camera_id, "status": "connecting", "message": "Restart requested"}


@router.post("/{camera_id}/status")
async def update_camera_status(
    camera_id: str, status_val: str, db: AsyncSession = Depends(get_db)
):
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    cam.status = status_val
    cam.updated_at = datetime.utcnow()
    await db.flush()
    return {"camera_id": camera_id, "status": status_val}


@router.get("/{camera_id}/diagnostics")
async def get_camera_diagnostics(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Returns real-time CV pipeline diagnostics for a camera."""
    cam = await db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    diag = engine_manager.get_diagnostics(camera_id)
    diag["db_status"] = cam.status
    diag["rtsp_url"] = cam.rtsp_url
    diag["name"] = cam.name
    diag["has_live_frame"] = engine_manager.get_latest_frame(camera_id) is not None
    return diag
