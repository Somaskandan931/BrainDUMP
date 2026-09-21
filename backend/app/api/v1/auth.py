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

from backend.app.core import config
from backend.app.api.v1.deps import get_current_user
from backend.app.auth.github_login import exchange_code_for_profile as exchange_github_code
from backend.app.auth.google_login import verify_google_id_token
from backend.app.auth.rate_limit import get_limiter, retry_after_message
from backend.app.auth.security import (
    create_access_token,
    create_state_token,
    decode_state_token,
    hash_password,
    verify_password,
)
from backend.app.db.database import get_db
from backend.app.models.user import User
from backend.app.services.workspace.activity_service import Action, log_activity
from backend.app.schemas.auth import (
    GithubLoginRequest,
    GoogleLoginRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from backend.app.services.email_service import send_password_reset_email, send_verification_email

router = APIRouter()

# --- Rate limiting -----------------------------------------------------------
# get_limiter() returns a Redis-backed limiter (shared across every API
# process/instance) when config.REDIS_URL is set and reachable, and the
# original in-memory one otherwise -- see auth/rate_limit.py.
_login_account_limiter = get_limiter(config.AUTH_LOGIN_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_login_ip_limiter = get_limiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_register_limiter = get_limiter(config.AUTH_REGISTER_MAX_PER_IP, config.AUTH_REGISTER_WINDOW_SECONDS)
_google_limiter = get_limiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_github_limiter = get_limiter(config.AUTH_LOGIN_IP_MAX_FAILURES, config.AUTH_LOGIN_WINDOW_SECONDS)
_verify_resend_limiter = get_limiter(
    config.AUTH_EMAIL_ACTION_MAX_PER_IP, config.AUTH_EMAIL_ACTION_WINDOW_SECONDS
)
_password_reset_limiter = get_limiter(
    config.AUTH_EMAIL_ACTION_MAX_PER_IP, config.AUTH_EMAIL_ACTION_WINDOW_SECONDS
)
_ALL_LIMITERS = (
    _login_account_limiter,
    _login_ip_limiter,
    _register_limiter,
    _google_limiter,
    _github_limiter,
    _verify_resend_limiter,
    _password_reset_limiter,
)

# Purpose tags for the short-lived signed tokens minted below (see
# auth/security.py's create_state_token/decode_state_token -- the same
# purpose-scoped-JWT mechanism the Google Calendar OAuth `state`
# parameter already uses, reused here instead of a new DB table since a
# verification/reset link is exactly that: a token that proves "the
# owner of this inbox clicked a link within N minutes", nothing more).
_PURPOSE_VERIFY_EMAIL = "verify_email"
_PURPOSE_PASSWORD_RESET = "password_reset"

# Generic response for both branches of password-reset request, so the
# response never reveals whether an email is registered (see login's
# _check_password for the same anti-enumeration principle).
_PASSWORD_RESET_GENERIC_MESSAGE = (
    "If an account exists for that email, we've sent a password reset link."
)


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


def _send_verification_email(user: User) -> None:
    token = create_state_token(
        user.id, _PURPOSE_VERIFY_EMAIL, expires_minutes=config.EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES
    )
    send_verification_email(user.email, token)


def _create_user(db: Session, user: User, method: str) -> User:
    """Insert a newly registered user and its audit row in ONE commit. The
    session here is unscoped (no user exists yet), so the audit row names
    its user explicitly."""
    db.add(user)
    db.flush()  # assigns user.id
    log_activity(
        db,
        Action.AUTH_REGISTERED,
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        details={"method": method},
    )
    db.commit()
    db.refresh(user)
    return user


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
        is_verified=False,
    )
    _create_user(db, user, "password")

    _send_verification_email(user)
    # Registration still returns a working token immediately even though
    # is_verified starts False -- config.EMAIL_VERIFICATION_REQUIRED (off
    # by default) is what actually gates login on it. This keeps
    # zero-SMTP local dev and existing callers working unchanged.
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
    if config.EMAIL_VERIFICATION_REQUIRED and not user.is_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Please verify your email before signing in. Check your inbox, or request a new link.",
        )

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
            is_verified=True,  # Google already proved the address
        )
        _create_user(db, user, "google")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    return _token_response(user)


@router.post("/github", response_model=TokenResponse)
def github_login(payload: GithubLoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
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
            is_verified=True,  # GitHub already proved the address
        )
        _create_user(db, user, "github")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


# --- Email verification --------------------------------------------------


@router.post("/verify-email/resend", response_model=MessageResponse)
def resend_verification_email(
    payload: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    """Same anti-enumeration shape as password-reset/request below: always
    200, regardless of whether the email is registered or already verified."""
    ip = _client_ip(request)
    _enforce(_verify_resend_limiter, ip)
    _verify_resend_limiter.hit(ip)

    user = _user_by_email(db, payload.email)
    if user is not None and user.is_active and not user.is_verified:
        _send_verification_email(user)
    return MessageResponse(message="If that account needs verifying, we've sent a new link.")


@router.post("/verify-email/confirm", response_model=MessageResponse)
def confirm_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user_id = decode_state_token(payload.token, _PURPOSE_VERIFY_EMAIL)
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This verification link is invalid or has expired.")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This verification link is invalid or has expired.")

    if not user.is_verified:
        user.is_verified = True
        log_activity(db, Action.AUTH_EMAIL_VERIFIED, entity_type="user", entity_id=user.id, user_id=user.id)
        db.commit()
    return MessageResponse(message="Your email is verified. You can sign in now.")


# --- Password reset --------------------------------------------------------


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(
    payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
) -> MessageResponse:
    ip = _client_ip(request)
    _enforce(_password_reset_limiter, ip)
    _password_reset_limiter.hit(ip)

    user = _user_by_email(db, payload.email)
    # Only a password account has a password to reset -- an OAuth-only user
    # (hashed_password is None) gets no email; they sign in with Google/GitHub.
    if user is not None and user.is_active and user.hashed_password is not None:
        token = create_state_token(
            user.id, _PURPOSE_PASSWORD_RESET, expires_minutes=config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
        send_password_reset_email(user.email, token)
    return MessageResponse(message=_PASSWORD_RESET_GENERIC_MESSAGE)


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user_id = decode_state_token(payload.token, _PURPOSE_PASSWORD_RESET)
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")

    user.hashed_password = hash_password(payload.new_password)
    # Never anything about the password itself in the trail -- just that it happened.
    log_activity(
        db,
        Action.AUTH_PASSWORD_RESET,
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        details={"also_verified_email": not user.is_verified},
    )
    db.commit()
    # A password reset is also proof of inbox ownership -- verify the
    # account at the same time so a user who never clicked the original
    # verification email isn't stuck locked out after recovering access.
    if not user.is_verified:
        user.is_verified = True
        db.commit()
    return MessageResponse(message="Your password has been reset. You can sign in now.")
