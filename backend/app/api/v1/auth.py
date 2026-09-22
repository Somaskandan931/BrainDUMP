"""
api/auth.py — /api/auth/register, /login, /google, /github, /refresh,
/logout, /me.

These are the only routes that depend on database.get_db directly
(there's no current_user yet to scope by) — everything else depends on
api.deps.get_scoped_db.

Session model (see auth/token_service.py for the mechanics): every
route that logs a user in also sets a long-lived refresh token as an
HttpOnly cookie, and returns a short-lived access token in the response
body as before. /refresh reads that cookie to mint a new access token
(and rotates the refresh token); /logout revokes it and clears the
cookie. The body-level access_token is unaffected for any caller that
doesn't use cookies (e.g. a script hitting the API directly) -- it just
now expires in config.ACCESS_TOKEN_EXPIRE_MINUTES instead of 7 days.

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
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.api.v1.deps import get_current_user
from backend.app.auth.github_login import exchange_code_for_profile as exchange_github_code
from backend.app.auth.google_login import verify_google_id_token
from backend.app.auth.rate_limit import RedisSlidingWindowLimiter, SlidingWindowLimiter, get_limiter, retry_after_message
from backend.app.auth.security import (
    create_access_token,
    create_action_token,
    decode_action_token,
    hash_password,
    verify_password,
)
from backend.app.auth.token_service import (
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    revoke_all_for_user,
)
from backend.app.db.database import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import (
    GithubLoginRequest,
    GoogleLoginRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from backend.app.services.email_service import send_password_reset_email, send_verification_email
from backend.app.services.workspace.activity_service import log_activity

router = APIRouter()

# --- Rate limiting -------------------------------------------------------------
# get_limiter() picks a Redis-backed limiter (shared across every API instance)
# when config.REDIS_URL is set and reachable, otherwise the original
# per-process in-memory limiter -- see auth/rate_limit.py.
_login_account_limiter = get_limiter(config.AUTH_LOGIN_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_login_ip_limiter = get_limiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_register_limiter = get_limiter(config.AUTH_REGISTER_MAX_PER_IP, config.AUTH_REGISTER_WINDOW_SECONDS)
_google_limiter = get_limiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_github_limiter = get_limiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_password_reset_limiter = get_limiter(10, 3600)
_ALL_LIMITERS = (
    _login_account_limiter, _login_ip_limiter, _register_limiter,
    _google_limiter, _github_limiter, _password_reset_limiter,
)


def reset_rate_limits() -> None:
    """Forget all limiter state (used by tests; also handy for an ops shell)."""
    for limiter in _ALL_LIMITERS:
        limiter.clear()


def _client_ip(request: Request) -> str:
    # Behind a proxy this is the real client only if uvicorn runs with
    # --proxy-headers (the deploy Dockerfile does); otherwise it's the proxy.
    return request.client.host if request.client else "unknown"


def _enforce(limiter: "SlidingWindowLimiter | RedisSlidingWindowLimiter", key: str) -> None:
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


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=config.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=config.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=config.REFRESH_COOKIE_PATH,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=config.REFRESH_COOKIE_NAME,
        path=config.REFRESH_COOKIE_PATH,
    )


def _issue_session(db: Session, response: Response, request: Request, user: User) -> TokenResponse:
    """Sets the HttpOnly refresh cookie as a side effect and returns the
    short-lived access token for the response body."""
    result = issue_refresh_token(db, user.id, user_agent=request.headers.get("user-agent"))
    _set_refresh_cookie(response, result.raw_token)
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


# --- Routes ------------------------------------------------------------------
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    ip = _client_ip(request)
    _enforce(_register_limiter, ip)
    _register_limiter.hit(ip)

    if _user_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=_norm_email(payload.email),
        name=payload.name,
        hashed_password=hash_password(payload.password),
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_activity(
        db, user_id=user.id, action="auth.registered", entity_type="user", entity_id=user.id,
        details={"method": "password"},
    )
    db.commit()

    # The session is intentionally issued so the existing response contract
    # remains stable, but protected routes reject unverified users. The refresh
    # cookie is therefore not an authentication bypass.
    token = create_action_token(user.id, "email_verification", config.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES)
    send_verification_email(user.email, token)
    return _issue_session(db, response, request, user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
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
    if config.EMAIL_VERIFICATION_REQUIRED and not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please verify your email address before signing in")

    _login_account_limiter.reset(account_key)
    return _issue_session(db, response, request, user)



@router.post("/verify-email/confirm", response_model=UserOut)
def confirm_email_verification(
    payload: VerifyEmailRequest, db: Session = Depends(get_db)
) -> UserOut:
    claims = decode_action_token(payload.token, "email_verification")
    if claims is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification token")

    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid verification token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification token")

    if not user.is_verified:
        user.is_verified = True
        log_activity(
            db, user_id=user.id, action="auth.email_verified",
            entity_type="user", entity_id=user.id,
        )
        db.commit()
        db.refresh(user)

    return UserOut.model_validate(user)


@router.post("/password-reset/request", status_code=status.HTTP_200_OK)
def request_password_reset(
    payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    """Always return the same response so email addresses cannot be enumerated."""
    ip = _client_ip(request)
    _enforce(_password_reset_limiter, ip)
    _password_reset_limiter.hit(ip)

    user = _user_by_email(db, payload.email)
    if user is not None and user.is_active and user.hashed_password is not None:
        token = create_action_token(
            user.id, "password_reset", config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            password_version=hashlib.sha256(user.hashed_password.encode("utf-8")).hexdigest(),
        )
        send_password_reset_email(user.email, token)

    return {"message": "If an account exists for that email, a password reset link has been sent."}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)
) -> None:
    claims = decode_action_token(payload.token, "password_reset")
    if claims is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired password reset token")

    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid password reset token")

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.hashed_password is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired password reset token")

    # Bind the reset token to the password hash that existed when the email
    # was requested. Changing the password therefore makes the same token
    # unusable even if the reset and replay happen within one clock second.
    current_password_version = hashlib.sha256(user.hashed_password.encode("utf-8")).hexdigest()
    if claims.get("password_version") != current_password_version:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired password reset token")

    user.hashed_password = hash_password(payload.new_password)
    user.is_verified = True
    log_activity(
        db, user_id=user.id, action="auth.password_reset",
        entity_type="user", entity_id=user.id,
    )
    db.commit()

    revoke_all_for_user(db, user.id)


@router.post("/google", response_model=TokenResponse)
def google_login(
    payload: GoogleLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
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
        log_activity(db, user_id=user.id, action="auth.registered", entity_type="user", entity_id=user.id, details={"method": "google"})

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    return _issue_session(db, response, request, user)


@router.post("/github", response_model=TokenResponse)
def github_login(
    payload: GithubLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    ip = _client_ip(request)
    _enforce(_github_limiter, ip)

    profile = exchange_github_code(payload.code)
    if profile is None:
        _github_limiter.hit(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid GitHub authorization code")

    user = db.query(User).filter(User.github_id == profile.sub).first()
    if user is None:
        if _user_by_email(db, profile.email) is not None:
            # Same account-takeover concern as Google above: don't
            # auto-link onto an existing password account by email match.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An account with this email already exists. Sign in with your email and password instead.",
            )
        user = User(
            email=_norm_email(profile.email),
            name=profile.name,
            github_id=profile.sub,
            github_avatar_url=profile.avatar_url,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        log_activity(db, user_id=user.id, action="auth.registered", entity_type="user", entity_id=user.id, details={"method": "github"})

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    return _issue_session(db, response, request, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    """Reads the HttpOnly refresh cookie, rotates it, and returns a new
    short-lived access token. 401 (and the cookie is cleared) if the
    cookie is missing, expired, or was already used once before -- the
    frontend should treat that as "signed out", not retry."""
    raw_token = request.cookies.get(config.REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh session")

    result = rotate_refresh_token(db, raw_token, user_agent=request.headers.get("user-agent"))
    if result is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session expired or revoked")

    user = db.get(User, result.row.user_id)
    if user is None or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session expired or revoked")
    if config.EMAIL_VERIFICATION_REQUIRED and not user.is_verified:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please verify your email address before signing in")

    _set_refresh_cookie(response, result.raw_token)
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    """Revokes the current refresh session (if any) and clears the cookie.
    Always succeeds, including with no cookie at all, so the frontend can
    call this unconditionally on "sign out" without checking state first."""
    raw_token = request.cookies.get(config.REFRESH_COOKIE_NAME)
    if raw_token:
        revoke_refresh_token(db, raw_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
