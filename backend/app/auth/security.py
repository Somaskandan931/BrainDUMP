"""
auth/security.py — password hashing and JWT create/decode.

Kept dependency-light and framework-agnostic on purpose: nothing here
touches FastAPI or the DB, so it's easy to unit test in isolation
(tests/test_auth.py) and to reuse from the /register, /login, and
get_current_user code paths without any of them importing each other.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.core import config

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    """`subject` is the user id, stored as the JWT `sub` claim (JWTs
    require string claims, so the caller's int id is stringified)."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else config.JWT_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Returns the decoded claims, or None for an invalid/expired token
    (never raises) — callers turn a None into a 401."""
    try:
        claims = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None
    # Purpose-scoped tokens (e.g. the OAuth `state` below) carry a "purpose"
    # claim and travel through browser URLs/history -- they must never be
    # accepted as a login bearer token, or leaking one would be a session leak.
    if "purpose" in claims:
        return None
    return claims


def create_state_token(user_id: int, purpose: str, expires_minutes: int = 10) -> str:
    """Short-lived, purpose-scoped signed token for round-tripping through a
    third party (the Google OAuth `state` parameter). Distinct from an
    access token: it carries a `purpose` claim, which decode_access_token
    rejects, and decode_state_token only accepts for the same purpose."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload: dict[str, Any] = {"sub": str(user_id), "purpose": purpose, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_state_token(token: str, purpose: str) -> int | None:
    """The user id inside a create_state_token() token, or None if it's
    invalid, expired, or was minted for a different purpose."""
    try:
        claims = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None
    if claims.get("purpose") != purpose:
        return None
    try:
        return int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        return None
