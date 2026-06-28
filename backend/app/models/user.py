"""
User model with role-based access control.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email:            Mapped[str]  = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name:        Mapped[str]  = mapped_column(String(255), nullable=False)
    hashed_password:  Mapped[str]  = mapped_column(String(255), nullable=False)
    role:             Mapped[str]  = mapped_column(String(20), nullable=False, default="viewer")  # admin|manager|viewer
    is_active:        Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified:      Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login:       Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Forced password change on first login
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Audit
    created_by:       Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    notes:            Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
