"""
RetailAI Agent — Production-grade configuration management.
Layered: defaults → .env file → environment variables → secrets.
"""
from __future__ import annotations

import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT  = "development"
    STAGING      = "staging"
    PRODUCTION   = "production"
    TEST         = "test"


class DatabaseDialect(str, Enum):
    SQLITE     = "sqlite"
    POSTGRESQL = "postgresql"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────
    APP_NAME:         str         = "RetailAI Agent"
    APP_VERSION:      str         = "1.0.0"
    API_V1_PREFIX:    str         = "/api/v1"
    ENVIRONMENT:      Environment = Environment.DEVELOPMENT
    DEBUG:            bool        = False
    LOG_LEVEL:        str         = "INFO"
    LOG_FORMAT:       Literal["json", "text"] = "json"

    # ── Security ───────────────────────────────────────────────────────
    SECRET_KEY:              str   = secrets.token_urlsafe(64)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    ENCRYPTION_KEY: str = "your-32-byte-fernet-key-here-1234567890123=" # For encrypting RTSP URLs    # 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7           # 7 days
    ALGORITHM:               str   = "HS256"
    BCRYPT_ROUNDS:           int   = 12

    # First-boot admin credentials (only used when DB is empty)
    ADMIN_EMAIL:    str = "admin@retailai.local"
    ADMIN_PASSWORD: str = "ChangeMe123!"  # Must be changed on first login
    ADMIN_NAME:     str = "System Administrator"

    # ── Database ───────────────────────────────────────────────────────
    DB_DIALECT:        DatabaseDialect = DatabaseDialect.SQLITE
    # SQLite path (used when DB_DIALECT=sqlite)
    SQLITE_PATH:       str             = "./data/db/retailai.db"
    # PostgreSQL DSN (used when DB_DIALECT=postgresql)
    POSTGRES_DSN:      str             = ""
    DB_POOL_SIZE:      int             = 5
    DB_MAX_OVERFLOW:   int             = 10
    DB_ECHO:           bool            = False

    # ── CORS ───────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    # ── Services ───────────────────────────────────────────────────────
    BACKEND_URL:   str = "http://localhost:8000"
    FRONTEND_URL:  str = "http://localhost:3000"
    HLS_BASE_URL:  str = "http://localhost:8888"

    # ── CV Pipeline ────────────────────────────────────────────────────
    CV_MODEL_PATH:          str   = "yolo11n.pt"
    CV_CONFIDENCE:          float = 0.45
    CV_IOU_THRESHOLD:       float = 0.45
    CV_INFERENCE_DEVICE:    str   = "cpu"
    CV_TARGET_FPS:          int   = 10
    CV_HEATMAP_GRID_SIZE:   int   = 100

    # ── Storage ────────────────────────────────────────────────────────
    DATA_DIR:       str = "./data"
    REPORTS_DIR:    str = "./data/reports"
    MODELS_DIR:     str = "./data/models"
    UPLOAD_DIR:     str = "./data/uploads"
    MAX_UPLOAD_MB:  int = 50

    # ── Feature Flags ──────────────────────────────────────────────────
    FEATURE_CLOUD_SYNC:    bool = False   # Always off for local-first
    FEATURE_FACIAL_RECOG:  bool = False   # Permanently disabled
    FEATURE_BIOMETRICS:    bool = False   # Permanently disabled

    # ── Rate Limiting ──────────────────────────────────────────────────
    RATE_LIMIT_ENABLED:    bool = True
    RATE_LIMIT_PER_MINUTE: int  = 300

    # ── Computed properties ────────────────────────────────────────────
    @property
    def database_url(self) -> str:
        if self.DB_DIALECT == DatabaseDialect.POSTGRESQL:
            if not self.POSTGRES_DSN:
                raise ValueError("POSTGRES_DSN must be set when DB_DIALECT=postgresql")
            return self.POSTGRES_DSN
        path = Path(self.SQLITE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path.resolve()}"

    @property
    def async_database_url(self) -> str:
        return self.database_url

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == Environment.DEVELOPMENT

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.is_production:
            if self.SECRET_KEY == secrets.token_urlsafe(64):
                raise ValueError("SECRET_KEY must be explicitly set in production")
            if self.ADMIN_PASSWORD == "ChangeMe123!":
                raise ValueError("ADMIN_PASSWORD must be changed in production")
        # Privacy enforcement — these must NEVER be enabled
        if self.FEATURE_FACIAL_RECOG:
            raise ValueError("FEATURE_FACIAL_RECOG cannot be enabled (privacy policy)")
        if self.FEATURE_BIOMETRICS:
            raise ValueError("FEATURE_BIOMETRICS cannot be enabled (privacy policy)")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
