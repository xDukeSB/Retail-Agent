"""
Dependency injection — provides DB sessions, authenticated users, and RBAC guards.
"""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.security import Role, has_permission, verify_access_token
from app.db.session import AsyncSessionLocal

logger = get_logger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


# ── Database ──────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async DB session; auto-rollback on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ── Config ────────────────────────────────────────────────────────────────────

def get_config() -> Settings:
    return get_settings()


# ── Current User ──────────────────────────────────────────────────────────────

class CurrentUser:
    """Lightweight user identity extracted from JWT — no DB hit required."""
    def __init__(self, user_id: str, email: str, role: Role, is_active: bool = True):
        self.user_id   = user_id
        self.email     = email
        self.role      = role
        self.is_active = is_active


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> CurrentUser:
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise auth_error

    payload = verify_access_token(credentials.credentials)
    if payload is None:
        raise auth_error

    try:
        return CurrentUser(
            user_id=payload["sub"],
            email=payload.get("email", ""),
            role=Role(payload["role"]),
            is_active=payload.get("is_active", True),
        )
    except (KeyError, ValueError):
        raise auth_error


async def get_current_active_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


# ── RBAC Guards ───────────────────────────────────────────────────────────────

def require_permission(permission: str):
    """
    Factory for permission-based dependencies.
    Usage: Depends(require_permission("cameras:write"))
    """
    async def _check(
        user: Annotated[CurrentUser, Depends(get_current_active_user)],
    ) -> CurrentUser:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} requires higher privileges",
            )
        return user
    return _check


def require_role(*roles: Role):
    """
    Factory for role-based dependencies.
    Usage: Depends(require_role(Role.ADMIN, Role.MANAGER))
    """
    async def _check(
        user: Annotated[CurrentUser, Depends(get_current_active_user)],
    ) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to: {', '.join(r.value for r in roles)}",
            )
        return user
    return _check


# ── Shorthand dependencies ─────────────────────────────────────────────────────

AdminOnly    = Depends(require_role(Role.ADMIN))
ManagerPlus  = Depends(require_role(Role.ADMIN, Role.MANAGER))
AnyRole      = Depends(get_current_active_user)

# Type aliases
DBDep       = Annotated[AsyncSession, Depends(get_db)]
ConfigDep   = Annotated[Settings, Depends(get_config)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_active_user)]
