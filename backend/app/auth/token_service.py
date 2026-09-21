"""
auth/token_service.py — issue, rotate, and revoke refresh tokens.

Session model: a short-lived access token (JWT, config.ACCESS_TOKEN_
EXPIRE_MINUTES) goes in the response body and is sent as a normal
`Authorization: Bearer` header, same as before. A long-lived refresh
token is a random, unguessable string whose SHA-256 hash is the only
thing ever persisted (models/refresh_token.py); the raw value is set
only as an HttpOnly cookie (api/v1/auth.py's _set_refresh_cookie), so
client-side JS -- and therefore XSS -- never has access to it.

Rotation + reuse detection: every /refresh call revokes the presented
token and issues a brand-new one (rotate_refresh_token). If a token that
is *already revoked* is presented again, that can only happen if it was
stolen and used after the legitimate client already rotated past it --
so the whole family is treated as compromised and every refresh token
the user has is revoked, forcing a fresh login everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.auth.security import generate_refresh_token, hash_refresh_token
from backend.app.core import config
from backend.app.models.refresh_token import RefreshToken


@dataclass
class RefreshResult:
    raw_token: str
    row: RefreshToken


def issue_refresh_token(db: Session, user_id: int, user_agent: str | None = None) -> RefreshResult:
    raw, token_hash = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RefreshResult(raw_token=raw, row=row)


def _revoke(db: Session, row: RefreshToken) -> None:
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)


def revoke_all_for_user(db: Session, user_id: int) -> None:
    """Used on password reset and on detected refresh-token reuse -- signs
    the user out of every device/browser, not just the current one."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .all()
    )
    for row in rows:
        row.revoked_at = now
    db.commit()


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """Used by /logout. A no-op if the token doesn't exist or is already
    revoked -- logout should never fail just because the cookie was stale."""
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw_token)).first()
    if row is None:
        return
    _revoke(db, row)
    db.commit()


def rotate_refresh_token(db: Session, raw_token: str, user_agent: str | None = None) -> RefreshResult | None:
    """Validates `raw_token`, and on success revokes it and returns a fresh
    one for the same user. Returns None (nothing to do but clear the
    cookie and 401) when the token is missing, expired, or already
    revoked once -- reuse of an already-revoked token additionally
    revokes every other live refresh token for that user (see module
    docstring)."""
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw_token)).first()
    if row is None:
        return None

    now = datetime.now(timezone.utc)
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)

    if row.revoked_at is not None:
        # Reuse of a token already rotated past -- treat the session as
        # compromised rather than trusting this presentation.
        revoke_all_for_user(db, row.user_id)
        return None

    if expires_at < now:
        _revoke(db, row)
        db.commit()
        return None

    new = issue_refresh_token(db, row.user_id, user_agent=user_agent)
    row.revoked_at = now
    row.replaced_by_id = new.row.id
    db.commit()
    return new
