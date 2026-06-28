"""
User management endpoints — Admin/Manager only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    AdminOnly, CurrentUserDep, DBDep, ManagerPlus,
    require_permission,
)
from app.core.logging import get_logger
from app.core.security import Role, hash_password
from app.models.user import User
from app.schemas.auth import (
    CreateUserRequest, UpdateUserRequest,
    UserListResponse, UserResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=UserListResponse, summary="List all users")
async def list_users(
    db: DBDep,
    _: None = Depends(require_permission("users:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Role | None = None,
    is_active: bool | None = None,
):
    q = select(User)
    if role:
        q = q.where(User.role == role.value)
    if is_active is not None:
        q = q.where(User.is_active == is_active)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size).order_by(User.created_at.desc())
    result = await db.execute(q)
    users  = result.scalars().all()

    return UserListResponse(total=total, items=list(users))


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Create user")
async def create_user(
    body: CreateUserRequest,
    current_user: CurrentUserDep,
    db: DBDep,
    _: None = Depends(require_permission("users:write")),
):
    # Only admins can create admin accounts
    if body.role == Role.ADMIN and current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can create admin accounts")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role.value,
        created_by=current_user.user_id,
        notes=body.notes,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("User created", extra={"user_id": user.id, "role": user.role, "by": current_user.user_id})
    return user


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user(
    user_id: str,
    db: DBDep,
    _: None = Depends(require_permission("users:read")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse, summary="Update user")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_user: CurrentUserDep,
    db: DBDep,
    _: None = Depends(require_permission("users:write")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Managers cannot promote to admin
    if body.role == Role.ADMIN and current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can assign the admin role")

    values = body.model_dump(exclude_none=True)
    if "role" in values:
        values["role"] = values["role"].value

    await db.execute(update(User).where(User.id == user_id).values(**values))
    await db.commit()
    await db.refresh(user)
    logger.info("User updated", extra={"user_id": user_id, "by": current_user.user_id})
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user")
async def delete_user(
    user_id: str,
    current_user: CurrentUserDep,
    db: DBDep,
    _: None = Depends(require_permission("users:delete")),
):
    if user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    logger.info("User deleted", extra={"user_id": user_id, "by": current_user.user_id})
