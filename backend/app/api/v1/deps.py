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

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.auth.security import decode_access_token
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

    return user


def get_scoped_db(current_user: User = Depends(get_current_user)):
    """The dependency every tenant-scoped route should use in place of
    database.get_db. Yields a Session with tenant filtering turned on
    for current_user, so every query the route makes against a
    user-owned table is automatically restricted to their rows."""
    db = SessionLocal()
    db.info["user_id"] = current_user.id
    try:
        yield db
    finally:
        db.close()
