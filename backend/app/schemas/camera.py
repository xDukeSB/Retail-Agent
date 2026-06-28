"""
Pydantic schemas for camera API endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateCameraRequest(BaseModel):
    name:         str   = Field(min_length=1, max_length=255)
    description:  str | None = None
    location:     str | None = None
    rtsp_url:     str   = Field(min_length=7)   # rtsp:// or http://
    username:     str | None = None
    password:     str | None = None
    fps_target:   int   = Field(default=10, ge=1, le=60)
    buffer_size:  int   = Field(default=30, ge=5, le=300)
    resolution_w: int | None = Field(default=None, ge=320, le=3840)
    resolution_h: int | None = Field(default=None, ge=240, le=2160)
    is_enabled:   bool  = True

    @field_validator("rtsp_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        allowed = ("rtsp://", "rtsps://", "rtmp://", "http://", "https://")
        if not any(v.startswith(p) for p in allowed):
            raise ValueError(f"URL must start with one of: {allowed}")
        return v

    @model_validator(mode="after")
    def validate_resolution(self) -> "CreateCameraRequest":
        if (self.resolution_w is None) != (self.resolution_h is None):
            raise ValueError("Both resolution_w and resolution_h must be set together")
        return self


class UpdateCameraRequest(BaseModel):
    name:         str | None = Field(default=None, min_length=1, max_length=255)
    description:  str | None = None
    location:     str | None = None
    rtsp_url:     str | None = None
    username:     str | None = None
    password:     str | None = None
    fps_target:   int | None = Field(default=None, ge=1, le=60)
    buffer_size:  int | None = Field(default=None, ge=5, le=300)
    resolution_w: int | None = None
    resolution_h: int | None = None
    is_enabled:   bool | None = None


class CameraResponse(BaseModel):
    id:               str
    name:             str
    description:      str | None
    location:         str | None
    rtsp_url:         str
    fps_target:       int
    buffer_size:      int
    resolution_w:     int | None
    resolution_h:     int | None
    status:           str
    last_seen_at:     datetime | None
    last_error:       str | None
    reconnect_count:  int
    avg_fps:          float | None
    is_active:        bool
    is_enabled:       bool
    created_at:       datetime
    updated_at:       datetime
    # Redact credentials
    has_credentials:  bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_redacted(cls, cam) -> "CameraResponse":
        data = cls.model_validate(cam)
        data.has_credentials = bool(cam.username)
        return data


class CameraHealthResponse(BaseModel):
    camera_id:        str
    state:            str
    avg_fps:          float
    target_fps:       int
    fps_ratio:        float
    frame_count:      int
    dropped_frames:   int
    drop_rate:        float
    reconnect_count:  int
    last_frame_at:    str | None
    last_error:       str | None
    uptime_seconds:   float
    latency_ms:       float | None
    resolution:       list[int] | None
    is_healthy:       bool
    is_streaming:     bool    # CameraService is actively running


class CameraListResponse(BaseModel):
    total:   int
    cameras: list[CameraResponse]
    summary: dict[str, Any]   # From CameraManager.get_summary()
