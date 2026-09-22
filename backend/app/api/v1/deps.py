"""
api/deps.py — FastAPI dependencies for authenticated, tenant-scoped requests.

get_current_user: Bearer token -> User row (401 if missing/invalid/expired
token, or the user no longer exists/is inactive).

get_scoped_db: wraps database.get_db, additionally stamping
session.info["user_id"] so database.py's do_orm_execute listener applies
row-level tenant filtering for the lifetime of the request. Every route
that touches a user-owned table should depend on this, not on
database.get_db directly.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.auth.security import decode_access_token
from backend.app.core import config
from backend.app.db.database import SessionLocal
from backend.app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _unscoped_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(_unscoped_db),
) -> User:
    if credentials is None:
        raise _CREDENTIALS_ERROR

    claims = decode_access_token(credentials.credentials)
    if claims is None or "sub" not in claims:
        raise _CREDENTIALS_ERROR

    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise _CREDENTIALS_ERROR

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR

    # core/request_logging.py's middleware reads this after the handler
    # returns so authenticated requests are attributed to a user_id in
    # the structured request log.
    request.state.user_id = user.id

    return user


_VERIFICATION_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Please verify your email address before using this",
)


def get_scoped_db(current_user: User = Depends(get_current_user)):
    """The dependency every tenant-scoped route should use in place of
    database.get_db. Yields a Session with tenant filtering turned on
    for current_user, so every query the route makes against a
    user-owned table is automatically restricted to their rows.

    Also enforces the verification gate documented in
    PRODUCTION_READINESS.md: "login, refresh, and tenant-scoped API
    access are blocked until verification." get_current_user alone
    intentionally does NOT enforce this, so purely account-level routes
    like /api/auth/me keep working for a freshly-registered, unverified
    user (they need to see their own pending-verification state); only
    routes that touch user-owned data are gated here.
    """
    if config.EMAIL_VERIFICATION_REQUIRED and not current_user.is_verified:
        raise _VERIFICATION_ERROR
    db = SessionLocal()
    db.info["user_id"] = current_user.id
    try:
        yield db
    finally:
        db.close()
