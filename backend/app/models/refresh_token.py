"""
models/refresh_token.py — SQLAlchemy model for RefreshToken.

Backs the HttpOnly-cookie session model (see auth/token_service.py and
api/v1/auth.py's /refresh, /logout routes). Only a SHA-256 hash of the
raw token is ever stored -- the raw value lives only in the browser's
HttpOnly cookie and briefly in memory here, the same way a password is
never stored in plaintext. A leaked database therefore never leaks a
usable session.

Rotation: each successful /refresh revokes the presented token and
issues a new one, linked back via replaced_by_id. This makes reuse of an
already-rotated (i.e. stolen and replayed) token detectable: if a
revoked token is presented again, token_service treats the whole chain
as compromised and revokes every refresh token the user has.

Deliberately NOT one of database.py's _tenant_models() -- it's looked up
by raw token during /refresh, before any authenticated user/session
exists to scope the query by, exactly like User itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base
from backend.app.models.mixins import TimestampMixin


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # SHA-256 hex digest of the raw token -- unique so a lookup is a plain
    # indexed equality check, never a hash comparison over every row.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Set on the OLD token when it is rotated, pointing at the new row --
    # a chain of these is how token_service tells "expected rotation" apart
    # from "someone replayed an old token after it was already rotated".
    replaced_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )

    # Best-effort, informational only (never used for any security decision).
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked_at is not None}>"
