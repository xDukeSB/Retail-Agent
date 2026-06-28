"""
Camera management REST API — production-grade with repository + service layers.

Endpoints:
  GET    /api/v1/cameras/                  List cameras (paginated, filterable)
  GET    /api/v1/cameras/stats             Status counts
  GET    /api/v1/cameras/{id}              Get single camera
  GET    /api/v1/cameras/{id}/health       Live stream health
  POST   /api/v1/cameras/                  Create camera
  POST   /api/v1/cameras/validate-url      Validate RTSP URL format
  POST   /api/v1/cameras/test-connection   Test RTSP connectivity
  PATCH  /api/v1/cameras/{id}             Update camera
  POST   /api/v1/cameras/{id}/restart     Force-restart stream
  POST   /api/v1/cameras/{id}/enable      Enable camera
  POST   /api/v1/cameras/{id}/disable     Disable camera
  DELETE /api/v1/cameras/{id}             Delete camera
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.deps import (
    CurrentUserDep, DBDep,
    require_permission,
)
from app.core.logging import get_logger
from app.db.camera_repository import camera_repo
from app.schemas.camera import (
    CameraHealthResponse, CameraListResponse,
    CameraResponse, CreateCameraRequest, UpdateCameraRequest,
)
from app.services.camera_manager import camera_manager
from app.services.camera_service_biz import camera_biz

logger = get_logger(__name__)
router = APIRouter(prefix="/cameras", tags=["Cameras"])


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _get_or_404(db, camera_id: str):
    cam = await camera_repo.find_by_id(db, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
    return cam


# ── GET /cameras/ ──────────────────────────────────────────────────────────────

@router.get("/", response_model=CameraListResponse, summary="List cameras")
async def list_cameras(
    db: DBDep,
    _: None = Depends(require_permission("cameras:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    include_inactive: bool = False,
):
    is_active = None if include_inactive else True
    offset    = (page - 1) * page_size
    total, cameras = await camera_repo.find_all(
        db,
        is_active=is_active,
        status=status_filter,
        limit=page_size,
        offset=offset,
    )
    return CameraListResponse(
        total=total,
        cameras=[CameraResponse.from_orm_redacted(c) for c in cameras],
        summary=camera_manager.get_summary(),
    )


# ── GET /cameras/stats ────────────────────────────────────────────────────────

@router.get("/stats", summary="Camera status counts")
async def camera_stats(
    db: DBDep,
    _: None = Depends(require_permission("cameras:read")),
):
    counts = await camera_repo.count_by_status(db)
    return {
        "by_status":       counts,
        "live_summary":    camera_manager.get_summary(),
        "active_ids":      camera_manager.get_active_camera_ids(),
    }


# ── GET /cameras/health/all ───────────────────────────────────────────────────

@router.get("/health/all", summary="All active stream health metrics")
async def all_health(
    _: None = Depends(require_permission("cameras:read")),
):
    raw = camera_manager.get_all_health()
    scored = {
        cid: {**h, "health_score": camera_biz.compute_health_score(h)}
        for cid, h in raw.items()
    }
    return {"cameras": scored, "summary": camera_manager.get_summary()}


# ── POST /cameras/validate-url ────────────────────────────────────────────────

class ValidateUrlRequest(BaseModel):
    url: str = Field(min_length=7)


@router.post("/validate-url", summary="Validate RTSP URL format (no network call)")
async def validate_url(
    body: ValidateUrlRequest,
    _: None = Depends(require_permission("cameras:read")),
):
    result = camera_biz.validate_rtsp_url(body.url)
    return result.to_dict()


# ── POST /cameras/test-connection ─────────────────────────────────────────────

class TestConnectionRequest(BaseModel):
    url:      str  = Field(min_length=7)
    username: str | None = None
    password: str | None = None
    timeout:  int  = Field(default=8, ge=3, le=30)


@router.post("/test-connection", summary="Test RTSP stream connectivity (network call)")
async def test_connection(
    body: TestConnectionRequest,
    _: None = Depends(require_permission("cameras:read")),
):
    logger.info("Connection test requested", extra={"url_host": body.url.split("@")[-1][:30]})
    result = await camera_biz.test_connection(
        rtsp_url=body.url,
        timeout_seconds=body.timeout,
        username=body.username,
        password=body.password,
    )
    return result.to_dict()


# ── GET /cameras/{id} ─────────────────────────────────────────────────────────

@router.get("/{camera_id}", response_model=CameraResponse, summary="Get camera by ID")
async def get_camera(
    camera_id: str,
    db: DBDep,
    _: None = Depends(require_permission("cameras:read")),
):
    cam = await _get_or_404(db, camera_id)
    return CameraResponse.from_orm_redacted(cam)


# ── GET /cameras/{id}/health ──────────────────────────────────────────────────

@router.get("/{camera_id}/health", response_model=CameraHealthResponse, summary="Live stream health")
async def get_health(
    camera_id: str,
    db: DBDep,
    _: None = Depends(require_permission("cameras:read")),
):
    cam    = await _get_or_404(db, camera_id)
    health = camera_manager.get_health(camera_id)
    svc    = camera_manager.get_service(camera_id)

    if health is None:
        return CameraHealthResponse(
            camera_id=camera_id,
            state="inactive",
            avg_fps=0.0,
            target_fps=cam.fps_target,
            fps_ratio=0.0,
            frame_count=0,
            dropped_frames=0,
            drop_rate=0.0,
            reconnect_count=cam.reconnect_count,
            last_frame_at=cam.last_seen_at.isoformat() if cam.last_seen_at else None,
            last_error=cam.last_error,
            uptime_seconds=0.0,
            latency_ms=None,
            resolution=None,
            is_healthy=False,
            is_streaming=False,
        )

    score = camera_biz.compute_health_score(health)
    return CameraHealthResponse(
        **health,
        is_streaming=svc.is_running if svc else False,
        health_score=score,
        health_label=camera_biz.get_health_label(score),
    )


# ── POST /cameras/ ────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=CameraResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new camera",
)
async def create_camera(
    body: CreateCameraRequest,
    current_user: CurrentUserDep,
    db: DBDep,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_permission("cameras:write")),
):
    # Business rule: no duplicate names
    if await camera_repo.find_by_name(db, body.name):
        raise HTTPException(status_code=409, detail=f"Camera named '{body.name}' already exists")

    # Business rule: no duplicate RTSP URLs
    if not await camera_biz.ensure_no_duplicate_url(db, body.rtsp_url):
        raise HTTPException(status_code=409, detail="A camera with this RTSP URL is already registered")

    # Validate URL format
    validation = camera_biz.validate_rtsp_url(body.rtsp_url)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=f"Invalid RTSP URL: {validation.error}")

    cam_data = body.model_dump()
    cam      = await camera_repo.create(db, cam_data)

    # Start stream in background if enabled
    if cam.is_enabled:
        background_tasks.add_task(_start_stream_background, cam)

    logger.info("Camera registered", extra={"camera_id": cam.id, "by": current_user.user_id})
    return CameraResponse.from_orm_redacted(cam)


async def _start_stream_background(cam) -> None:
    try:
        await camera_manager.add_camera(cam)
    except Exception as exc:
        logger.error("Background stream start failed", extra={"camera_id": cam.id, "error": str(exc)})


# ── PATCH /cameras/{id} ───────────────────────────────────────────────────────

@router.patch("/{camera_id}", response_model=CameraResponse, summary="Update camera config")
async def update_camera(
    camera_id: str,
    body: UpdateCameraRequest,
    current_user: CurrentUserDep,
    db: DBDep,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_permission("cameras:write")),
):
    cam     = await _get_or_404(db, camera_id)
    updates = body.model_dump(exclude_none=True)

    # Validate new URL if changed
    if "rtsp_url" in updates:
        v = camera_biz.validate_rtsp_url(updates["rtsp_url"])
        if not v.valid:
            raise HTTPException(status_code=422, detail=f"Invalid RTSP URL: {v.error}")
        if not await camera_biz.ensure_no_duplicate_url(db, updates["rtsp_url"], exclude_id=camera_id):
            raise HTTPException(status_code=409, detail="Another camera uses this RTSP URL")

    updated = await camera_repo.update(db, camera_id, updates)

    # Restart stream if connection-relevant fields changed
    restart_fields = {"rtsp_url", "fps_target", "buffer_size", "username", "password", "resolution_w", "resolution_h"}
    if updates.keys() & restart_fields:
        background_tasks.add_task(camera_manager.restart_camera, camera_id)

    logger.info("Camera updated", extra={"camera_id": camera_id, "by": current_user.user_id, "fields": list(updates.keys())})
    return CameraResponse.from_orm_redacted(updated)


# ── POST /cameras/{id}/restart ────────────────────────────────────────────────

@router.post("/{camera_id}/restart", summary="Force-restart stream")
async def restart_camera(
    camera_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    _: None = Depends(require_permission("cameras:write")),
):
    cam = await _get_or_404(db, camera_id)
    ok  = await camera_manager.restart_camera(camera_id)
    if not ok:
        await camera_manager.add_camera(cam)
    logger.info("Camera restarted", extra={"camera_id": camera_id, "by": current_user.user_id})
    return {"message": f"Camera '{cam.name}' stream restarted"}


# ── POST /cameras/{id}/enable|disable ────────────────────────────────────────

@router.post("/{camera_id}/enable", summary="Enable camera")
async def enable_camera(
    camera_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    _: None = Depends(require_permission("cameras:write")),
):
    cam = await _get_or_404(db, camera_id)
    await camera_repo.update(db, camera_id, {"is_enabled": True})
    await camera_manager.add_camera(cam)
    return {"message": f"Camera '{cam.name}' enabled"}


@router.post("/{camera_id}/disable", summary="Disable camera")
async def disable_camera(
    camera_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    _: None = Depends(require_permission("cameras:write")),
):
    cam = await _get_or_404(db, camera_id)
    await camera_repo.update(db, camera_id, {"is_enabled": False, "status": "inactive"})
    await camera_manager.remove_camera(camera_id)
    return {"message": f"Camera '{cam.name}' disabled"}


# ── DELETE /cameras/{id} ──────────────────────────────────────────────────────

@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete camera")
async def delete_camera(
    camera_id: str,
    current_user: CurrentUserDep,
    db: DBDep,
    _: None = Depends(require_permission("cameras:delete")),
):
    await _get_or_404(db, camera_id)
    await camera_manager.remove_camera(camera_id)
    await camera_repo.delete(db, camera_id)
    logger.info("Camera deleted", extra={"camera_id": camera_id, "by": current_user.user_id})
