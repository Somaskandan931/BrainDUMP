"""
api/auth.py — /api/auth/register, /login, /google, /me.

These are the only routes that depend on database.get_db directly
(there's no current_user yet to scope by) — everything else depends on
api.deps.get_scoped_db.

Hardening (see also auth/rate_limit.py):
- Brute-force limits: 429 + Retry-After after too many failed logins for an
  (IP, email) pair or from one IP, and too many registrations / Google
  sign-ins from one IP. Unknown emails count like wrong passwords.
- Login does the same amount of password-hashing work whether or not the
  account exists, so response time doesn't reveal which emails are registered.
- Emails are matched case-insensitively and stored lowercase.
- Google sign-in never *links* onto an existing password account. Nothing
  verifies that whoever registered an email actually owns it, so auto-linking
  would let someone pre-register a victim's address and keep access after the
  victim signed in with Google. The owner is told to use their password.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import config
from backend.api.deps import get_current_user
from backend.auth.google_login import verify_google_id_token
from backend.auth.rate_limit import SlidingWindowLimiter, retry_after_message
from backend.auth.security import create_access_token, hash_password, verify_password
from backend.database import get_db
from backend.models.user import User
from backend.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter()

# --- Rate limiting -----------------------------------------------------------
_login_account_limiter = SlidingWindowLimiter(config.AUTH_LOGIN_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_login_ip_limiter = SlidingWindowLimiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_register_limiter = SlidingWindowLimiter(config.AUTH_REGISTER_MAX_PER_IP, config.AUTH_REGISTER_WINDOW_SECONDS)
_google_limiter = SlidingWindowLimiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_ALL_LIMITERS = (_login_account_limiter, _login_ip_limiter, _register_limiter, _google_limiter)


def reset_rate_limits() -> None:
    """Forget all limiter state (used by tests; also handy for an ops shell)."""
    for limiter in _ALL_LIMITERS:
        limiter.clear()


def _client_ip(request: Request) -> str:
    # Behind a proxy this is the real client only if uvicorn runs with
    # --proxy-headers (the deploy Dockerfile does); otherwise it's the proxy.
    return request.client.host if request.client else "unknown"


def _enforce(limiter: SlidingWindowLimiter, key: str) -> None:
    wait = limiter.blocked_for(key)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after_message(wait),
            headers={"Retry-After": str(wait)},
        )


# --- Helpers -----------------------------------------------------------------
_dummy_hash: Optional[str] = None


def _check_password(password: str, hashed: Optional[str]) -> bool:
    """verify_password that costs the same when there is no hash to check
    (unknown email, or a Google-only account), so timing can't enumerate accounts."""
    global _dummy_hash
    if hashed is None:
        if _dummy_hash is None:
            _dummy_hash = hash_password("timing-equalisation-placeholder")
        verify_password(password, _dummy_hash)
        return False
    return verify_password(password, hashed)


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(func.lower(User.email) == _norm_email(email)).first()


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


# --- Routes ------------------------------------------------------------------
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    _enforce(_register_limiter, ip)
    _register_limiter.hit(ip)

    if _user_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=_norm_email(payload.email),
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    account_key = f"{ip}|{_norm_email(payload.email)}"
    _enforce(_login_ip_limiter, ip)
    _enforce(_login_account_limiter, account_key)

    user = _user_by_email(db, payload.email)
    password_ok = _check_password(payload.password, user.hashed_password if user else None)
    if user is None or not password_ok:
        _login_ip_limiter.hit(ip)
        _login_account_limiter.hit(account_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    _login_account_limiter.reset(account_key)
    return _token_response(user)


@router.post("/google", response_model=TokenResponse)
def google_login(payload: GoogleLoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    _enforce(_google_limiter, ip)

    profile = verify_google_id_token(payload.id_token)
    if profile is None:
        _google_limiter.hit(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token")

    user = db.query(User).filter(User.google_sub == profile.sub).first()
    if user is None:
        if _user_by_email(db, profile.email) is not None:
            # An account with this email exists but isn't tied to this Google
            # identity. Linking automatically would be an account-takeover path
            # (see module docstring), so refuse and point them at the password.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An account with this email already exists. Sign in with your email and password instead.",
            )
        user = User(
            email=_norm_email(profile.email),
            name=profile.name,
            google_sub=profile.sub,
            google_picture_url=profile.picture,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
