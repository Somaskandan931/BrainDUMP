"""
models/user.py — SQLAlchemy model for User.

Supports three login methods, any combination of:
- Email + password (hashed_password set, passlib/bcrypt)
- Google Sign-In (google_sub set, the stable "sub" claim from the
  verified Google ID token — see auth/google_login.py)
- GitHub OAuth (github_id set, GitHub's numeric account id from the
  verified access-token exchange — see auth/github_login.py)

The CHECK constraint below guarantees a row can never be created with
none of the three set (would be an unusable, unreachable account).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base
from backend.app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "hashed_password IS NOT NULL OR google_sub IS NOT NULL OR github_id IS NOT NULL",
            name="ck_users_has_login_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Null when the account was created via an OAuth provider only.
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # The Google ID token's stable "sub" claim. Null when the account was
    # never signed into with Google. Unique when present so the same
    # Google account can't be linked to two different local accounts.
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    google_picture_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # GitHub's numeric account id (stable even across a username/email
    # change, unlike GitHub's login handle) — see auth/github_login.py.
    # Null when the account was never signed into with GitHub.
    github_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    github_avatar_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # True from creation for Google/GitHub accounts (the provider already
    # proved the address). False for a fresh email+password registration
    # until the owner clicks the link from services/email_service.py --
    # see api/v1/auth.py's /verify-email/* routes and config.py's
    # EMAIL_VERIFICATION_REQUIRED for whether login actually enforces this.
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
