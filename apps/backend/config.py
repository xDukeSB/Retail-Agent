"""
Application configuration — reads from environment / .env file.
"""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Backend ──────────────────────────────────────
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_SECRET_KEY: str = "dev-secret-change-in-production"
    BACKEND_DEBUG: bool = False

    # ── JWT Auth ─────────────────────────────────────
    JWT_SECRET: str = "CHANGE-THIS-IN-PRODUCTION-USE-64-CHAR-RANDOM-STRING"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ── Database ─────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db/retailai.db"
    DB_DIR: str = "./data/db"

    # ── CORS ─────────────────────────────────────────
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]

    # ── Streaming ────────────────────────────────────
    MEDIAMTX_HOST: str = "localhost"
    MEDIAMTX_RTSP_PORT: int = 8554
    MEDIAMTX_HLS_PORT: int = 8888
    MEDIAMTX_API_PORT: int = 9997

    # ── Reports ──────────────────────────────────────
    REPORTS_OUTPUT_DIR: str = "./data/reports"
    STORE_NAME: str = "My Retail Store"
    STORE_TIMEZONE: str = "Asia/Kolkata"

    # ── Cloud Sync (Phase 2) ──────────────────────────
    CLOUD_SYNC_ENABLED: bool = False
    CLOUD_DATABASE_URL: str = ""
    CLOUD_API_KEY: str = ""
    CLOUD_SYNC_INTERVAL_SECONDS: int = 300

    # ── Aggregation ──────────────────────────────────
    AGGREGATION_INTERVAL_SECONDS: int = 60


settings = Settings()
