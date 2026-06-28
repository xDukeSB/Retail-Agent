"""
Authentication endpoints — login, refresh, logout, change password.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, DBDep, get_current_user
from app.core.logging import get_logger
from app.core.security import (
    Role, create_access_token, create_refresh_token,
    decode_token, verify_password,
)
from app.core.config import get_settings
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse,
)
from app.core.security import hash_password

logger   = get_logger(__name__)
router   = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse, summary="Obtain JWT tokens")
async def login(body: LoginRequest, db: DBDep):
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        logger.warning("Failed login attempt", extra={"email": body.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Update last login timestamp
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()

    role           = Role(user.role)
    access_token   = create_access_token(
        subject=user.id,
        role=role,
        extra={"email": user.email, "is_active": user.is_active},
    )
    refresh_token  = create_refresh_token(subject=user.id)

    logger.info("User logged in", extra={"user_id": user.id, "role": role.value})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MIN * 60,
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(body: RefreshRequest, db: DBDep):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user_id = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    role          = Role(user.role)
    access_token  = create_access_token(
        subject=user.id,
        role=role,
        extra={"email": user.email, "is_active": user.is_active},
    )
    new_refresh   = create_refresh_token(subject=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MIN * 60,
    )


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(current_user: CurrentUserDep, db: DBDep):
    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/change-password", summary="Change own password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUserDep,
    db: DBDep,
):
    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            hashed_password=hash_password(body.new_password),
            must_change_password=False,
        )
    )
    await db.commit()
    logger.info("Password changed", extra={"user_id": user.id})
    return {"message": "Password updated successfully"}


@router.post("/logout", summary="Logout (client-side token discard)")
async def logout(current_user: CurrentUserDep):
    # Stateless JWT — client discards token. Future: add token blacklist.
    logger.info("User logged out", extra={"user_id": current_user.user_id})
    return {"message": "Logged out successfully"}
