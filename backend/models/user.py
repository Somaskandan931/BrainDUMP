"""
models/user.py — SQLAlchemy model for User.

Supports two login methods, either or both:
- Email + password (hashed_password set, passlib/bcrypt)
- Google Sign-In (google_sub set, the stable "sub" claim from the
  verified Google ID token — see auth/google_login.py)

The CHECK constraint below guarantees a row can never be created with
neither method set (would be an unusable, unreachable account).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "hashed_password IS NOT NULL OR google_sub IS NOT NULL",
            name="ck_users_has_login_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Null when the account was created via Google only.
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # The Google ID token's stable "sub" claim. Null when the account was
    # created via email/password only. Unique when present so the same
    # Google account can't be linked to two different local accounts.
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    google_picture_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
