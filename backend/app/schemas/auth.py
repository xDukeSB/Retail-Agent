"""
Pydantic schemas for authentication endpoints.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import Role


# ── Request schemas ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str = Field(min_length=10)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ── Response schemas ───────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int  # seconds


class UserResponse(BaseModel):
    id:           str
    email:        str
    full_name:    str
    role:         Role
    is_active:    bool
    is_verified:  bool
    last_login:   datetime | None
    created_at:   datetime
    must_change_password: bool

    model_config = {"from_attributes": True}


# ── User management schemas ────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email:      EmailStr
    full_name:  str = Field(min_length=2, max_length=255)
    password:   str = Field(min_length=10)
    role:       Role = Role.VIEWER
    notes:      str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UpdateUserRequest(BaseModel):
    full_name:  str | None = None
    role:       Role | None = None
    is_active:  bool | None = None
    notes:      str | None = None


class UserListResponse(BaseModel):
    total:  int
    items:  list[UserResponse]
