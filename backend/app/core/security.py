"""
Security module — JWT tokens, password hashing, role definitions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── Role Definitions ───────────────────────────────────────────────────────────

class Role(str, Enum):
    ADMIN   = "admin"    # Full system access
    MANAGER = "manager"  # Read + export + camera management
    VIEWER  = "viewer"   # Read-only dashboard access


ROLE_HIERARCHY: dict[Role, int] = {
    Role.ADMIN:   3,
    Role.MANAGER: 2,
    Role.VIEWER:  1,
}

# Permission matrix — maps permission name → minimum role level
PERMISSIONS: dict[str, Role] = {
    # Analytics (read)
    "analytics:read":       Role.VIEWER,
    "timeline:read":        Role.VIEWER,
    "heatmap:read":         Role.VIEWER,
    "queue:read":           Role.VIEWER,
    "reports:read":         Role.VIEWER,
    # Reports (export)
    "reports:export":       Role.MANAGER,
    # Camera management
    "cameras:read":         Role.VIEWER,
    "cameras:write":        Role.MANAGER,
    "cameras:delete":       Role.ADMIN,
    # Zone management
    "zones:write":          Role.MANAGER,
    # User management
    "users:read":           Role.MANAGER,
    "users:write":          Role.ADMIN,
    "users:delete":         Role.ADMIN,
    # System
    "system:config":        Role.ADMIN,
    "system:health":        Role.VIEWER,  # Health is public
}


def has_permission(role: Role, permission: str) -> bool:
    required_role = PERMISSIONS.get(permission)
    if required_role is None:
        return False
    return ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[required_role]


# ── Password Hashing ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode(), salt).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT Tokens ─────────────────────────────────────────────────────────────────

class TokenType(str, Enum):
    ACCESS  = "access"
    REFRESH = "refresh"


def create_access_token(subject: str, role: Role, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MIN)
    payload: dict[str, Any] = {
        "sub":  subject,
        "role": role.value,
        "type": TokenType.ACCESS.value,
        "exp":  expire,
        "iat":  datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub":  subject,
        "type": TokenType.REFRESH.value,
        "exp":  expire,
        "iat":  datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def verify_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = decode_token(token)
        if payload.get("type") != TokenType.ACCESS.value:
            return None
        return payload
    except JWTError as exc:
        logger.debug("JWT validation failed", extra={"error": str(exc)})
        return None
