"""Auth: /api/auth/*, JWT handling, and the guarantee that every other route is protected."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt

from backend.app.core import config
from backend.app.auth import security
from backend.app.db.database import SessionLocal
from backend.app.models.user import User
from tests.helpers import TEST_PASSWORD, auth_headers, make_user

_PUBLIC_PATHS = {"/api/auth/register", "/api/auth/login", "/api/auth/google", "/api/auth/github", "/health"}


# ---------------------------------------------------------------------------
# Register / login
# ---------------------------------------------------------------------------

def test_register_returns_a_working_token(anon_client):
    res = anon_client.post(
        "/api/auth/register", json={"email": "new@example.com", "password": "a-decent-password", "name": "New"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["email"] == "new@example.com"
    assert "hashed_password" not in body["user"]

    me = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


def test_register_stores_a_hash_not_the_password(anon_client):
    """Also the regression for bcrypt>=5 breaking passlib: hashing must actually work."""
    anon_client.post("/api/auth/register", json={"email": "h@example.com", "password": "a-decent-password"})
    with SessionLocal() as session:
        stored = session.query(User).filter(User.email == "h@example.com").one().hashed_password
    assert stored and stored != "a-decent-password" and stored.startswith("$2")


def test_register_rejects_duplicate_email_and_short_password(anon_client):
    payload = {"email": "dup@example.com", "password": "a-decent-password"}
    assert anon_client.post("/api/auth/register", json=payload).status_code == 201
    assert anon_client.post("/api/auth/register", json=payload).status_code == 409
    assert anon_client.post("/api/auth/register", json={"email": "s@example.com", "password": "short"}).status_code == 422


def test_login_success_and_failures(anon_client):
    make_user("login@example.com")

    ok = anon_client.post("/api/auth/login", json={"email": "login@example.com", "password": TEST_PASSWORD})
    assert ok.status_code == 200 and ok.json()["access_token"]

    wrong = anon_client.post("/api/auth/login", json={"email": "login@example.com", "password": "nope-nope-nope"})
    unknown = anon_client.post("/api/auth/login", json={"email": "ghost@example.com", "password": TEST_PASSWORD})
    assert wrong.status_code == 401 and unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no user enumeration


def test_google_only_account_cannot_password_login(anon_client):
    with SessionLocal() as session:
        session.add(User(email="g@example.com", google_sub="google-sub-1"))
        session.commit()
    res = anon_client.post("/api/auth/login", json={"email": "g@example.com", "password": TEST_PASSWORD})
    assert res.status_code == 401


def test_google_login_is_refused_when_no_client_id_is_configured(anon_client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_LOGIN_CLIENT_ID", "")
    assert anon_client.post("/api/auth/google", json={"id_token": "whatever"}).status_code == 401


def test_github_only_account_cannot_password_login(anon_client):
    with SessionLocal() as session:
        session.add(User(email="gh@example.com", github_id="github-id-1"))
        session.commit()
    res = anon_client.post("/api/auth/login", json={"email": "gh@example.com", "password": TEST_PASSWORD})
    assert res.status_code == 401


def test_github_login_is_refused_when_not_configured(anon_client, monkeypatch):
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "")
    monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "")
    assert anon_client.post("/api/auth/github", json={"code": "whatever"}).status_code == 401


def test_github_login_does_not_auto_link_an_existing_password_account(anon_client, monkeypatch):
    """Same account-takeover guard as Google (see api/auth.py's module
    docstring): a GitHub profile whose email matches an existing
    password account must be refused, not silently linked."""
    make_user("shared@example.com")

    def fake_exchange(code: str):
        from backend.app.auth.github_login import GithubProfile

        return GithubProfile(sub="gh-999", email="shared@example.com", name="Someone", avatar_url=None)

    monkeypatch.setattr("backend.app.api.v1.auth.exchange_github_code", fake_exchange)
    res = anon_client.post("/api/auth/github", json={"code": "whatever"})
    assert res.status_code == 409


def test_deactivated_user_is_locked_out_everywhere(anon_client):
    user = make_user("gone@example.com")
    headers = auth_headers(user)
    assert anon_client.get("/api/auth/me", headers=headers).status_code == 200

    with SessionLocal() as session:
        session.get(User, user.id).is_active = False
        session.commit()

    assert anon_client.get("/api/auth/me", headers=headers).status_code == 401  # existing token stops working
    assert anon_client.get("/api/tasks/", headers=headers).status_code == 401
    login = anon_client.post("/api/auth/login", json={"email": "gone@example.com", "password": TEST_PASSWORD})
    assert login.status_code == 403


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def test_missing_malformed_and_tampered_tokens_are_401(anon_client, user):
    assert anon_client.get("/api/auth/me").status_code == 401
    assert anon_client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401

    forged = jwt.encode({"sub": str(user.id)}, "some-other-secret", algorithm=config.JWT_ALGORITHM)
    assert anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_expired_token_is_401(anon_client, user):
    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        config.JWT_SECRET_KEY,
        algorithm=config.JWT_ALGORITHM,
    )
    assert anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_token_for_a_nonexistent_user_is_401(anon_client):
    ghost = security.create_access_token(999_999)
    assert anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401


def test_oauth_state_token_cannot_be_used_as_a_login_token(anon_client, user):
    """The state token travels through the browser URL to Google and back; if it
    doubled as a bearer token, leaking one would leak a session."""
    state = security.create_state_token(user.id, "google_calendar_oauth")
    assert security.decode_access_token(state) is None
    assert anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {state}"}).status_code == 401


def test_state_token_is_bound_to_its_purpose_and_expires(user):
    token = security.create_state_token(user.id, "purpose-a")
    assert security.decode_state_token(token, "purpose-a") == user.id
    assert security.decode_state_token(token, "purpose-b") is None

    # an ordinary access token has no purpose, so it isn't a valid state token either
    assert security.decode_state_token(security.create_access_token(user.id), "purpose-a") is None

    expired = security.create_state_token(user.id, "purpose-a", expires_minutes=-1)
    assert security.decode_state_token(expired, "purpose-a") is None
    assert security.decode_state_token("garbage", "purpose-a") is None


# ---------------------------------------------------------------------------
# Every data route is protected
# ---------------------------------------------------------------------------

def _concrete(path: str) -> str:
    out, in_param = [], False
    for ch in path:
        if ch == "{":
            in_param = True
            out.append("1")
        elif ch == "}":
            in_param = False
        elif not in_param:
            out.append(ch)
    return "".join(out)


def test_every_non_public_route_rejects_anonymous_requests(anon_client):
    """Guard against a new router shipping on database.get_db (unscoped, unauthenticated)
    instead of api.deps.get_scoped_db: any /api route not on the public list must 401."""
    from backend.app.main import app

    unprotected = []
    for path, operations in app.openapi()["paths"].items():
        if path in _PUBLIC_PATHS:
            continue
        for method in operations:
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            res = anon_client.request(method.upper(), _concrete(path), json={} if method != "get" else None)
            if res.status_code != 401:
                unprotected.append(f"{method.upper()} {path} -> {res.status_code}")

    assert unprotected == []


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _login(client, email, password, **kw):
    return client.post("/api/auth/login", json={"email": email, "password": password}, **kw)


def test_repeated_failed_logins_get_429_with_retry_after(anon_client):
    make_user("brute@example.com")
    for _ in range(config.AUTH_LOGIN_MAX_FAILURES):
        assert _login(anon_client, "brute@example.com", "wrong-wrong-wrong").status_code == 401

    blocked = _login(anon_client, "brute@example.com", "wrong-wrong-wrong")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0 and "Try again" in blocked.json()["detail"]

    # once locked out, even the *correct* password is refused -- otherwise the limit would
    # only slow an attacker down by one guess per lockout instead of stopping the loop
    assert _login(anon_client, "brute@example.com", TEST_PASSWORD).status_code == 429


def test_unknown_emails_are_limited_exactly_like_real_ones(anon_client):
    """A 429 (or its absence) must not reveal whether an account exists."""
    for _ in range(config.AUTH_LOGIN_MAX_FAILURES):
        assert _login(anon_client, "ghost@example.com", "whatever-pw").status_code == 401
    assert _login(anon_client, "ghost@example.com", "whatever-pw").status_code == 429


def test_successful_login_clears_the_accounts_failure_count(anon_client):
    make_user("ok@example.com")
    for _ in range(config.AUTH_LOGIN_MAX_FAILURES - 1):
        _login(anon_client, "ok@example.com", "wrong-wrong-wrong")
    assert _login(anon_client, "ok@example.com", TEST_PASSWORD).status_code == 200

    for _ in range(config.AUTH_LOGIN_MAX_FAILURES - 1):  # a fresh budget, not the leftover one
        assert _login(anon_client, "ok@example.com", "wrong-wrong-wrong").status_code == 401


def test_one_ip_spraying_many_emails_is_stopped_by_the_per_ip_limit(anon_client):
    for i in range(config.AUTH_LOGIN_IP_MAX_FAILURES):
        assert _login(anon_client, f"victim{i}@example.com", "guess-guess").status_code == 401
    assert _login(anon_client, "fresh-email@example.com", "guess-guess").status_code == 429


def test_lockout_is_per_ip_so_a_stranger_cannot_lock_out_the_owner(anon_client):
    make_user("owner@example.com")
    for _ in range(config.AUTH_LOGIN_MAX_FAILURES):
        _login(anon_client, "owner@example.com", "wrong-wrong-wrong", headers={"X-Forwarded-For": "1.1.1.1"})

    # TestClient's peer address doesn't follow X-Forwarded-For, so simulate a different
    # client by keying a different (ip|email) pair directly
    from backend.app.api.v1 import auth as auth_api

    assert auth_api._login_account_limiter.blocked_for("testclient|owner@example.com") is not None
    assert auth_api._login_account_limiter.blocked_for("203.0.113.9|owner@example.com") is None


def test_registration_is_limited_per_ip(anon_client):
    for i in range(config.AUTH_REGISTER_MAX_PER_IP):
        assert anon_client.post(
            "/api/auth/register", json={"email": f"bulk{i}@example.com", "password": "a-decent-password"}
        ).status_code == 201
    over = anon_client.post("/api/auth/register", json={"email": "one-more@example.com", "password": "a-decent-password"})
    assert over.status_code == 429 and "Retry-After" in over.headers


def test_google_sign_in_attempts_with_bad_tokens_are_limited(anon_client, monkeypatch):
    from backend.app.api.v1 import auth as auth_api

    monkeypatch.setattr(auth_api, "verify_google_id_token", lambda token: None)
    for _ in range(config.AUTH_LOGIN_IP_MAX_FAILURES):
        assert anon_client.post("/api/auth/google", json={"id_token": "x"}).status_code == 401
    assert anon_client.post("/api/auth/google", json={"id_token": "x"}).status_code == 429


def test_the_limiter_window_slides_and_expires():
    from backend.app.auth.rate_limit import SlidingWindowLimiter

    now = [1000.0]
    limiter = SlidingWindowLimiter(max_events=3, window_seconds=60, clock=lambda: now[0])

    for _ in range(3):
        limiter.hit("k")
        now[0] += 10
    assert limiter.blocked_for("k") == 30  # the oldest of the three (t=1000) ages out at t=1060, now=1030
    assert limiter.blocked_for("someone-else") is None

    now[0] = 1061
    assert limiter.blocked_for("k") is None  # oldest event expired -> only 2 left in window

    limiter.hit("k")
    assert limiter.blocked_for("k") is not None
    limiter.reset("k")
    assert limiter.blocked_for("k") is None


def test_the_limiter_bounds_its_memory():
    from backend.app.auth import rate_limit

    limiter = rate_limit.SlidingWindowLimiter(1, 60)
    original = rate_limit._MAX_KEYS
    rate_limit._MAX_KEYS = 50
    try:
        for i in range(500):
            limiter.hit(f"key-{i}")
        assert len(limiter._events) <= 50
    finally:
        rate_limit._MAX_KEYS = original


# ---------------------------------------------------------------------------
# Login hardening
# ---------------------------------------------------------------------------

def test_unknown_email_still_costs_a_password_hash(anon_client, monkeypatch):
    """Skipping the bcrypt check for unknown emails made "no such account" measurably
    faster than "wrong password", which lets an attacker enumerate registered emails."""
    from backend.app.api.v1 import auth as auth_api

    calls = []
    real = auth_api.verify_password
    monkeypatch.setattr(auth_api, "verify_password", lambda pw, h: calls.append(h) or real(pw, h))

    assert _login(anon_client, "nobody@example.com", "some-password").status_code == 401
    assert len(calls) == 1


def test_emails_are_case_insensitive_and_stored_lowercase(anon_client):
    res = anon_client.post("/api/auth/register", json={"email": "Mixed.Case@Example.com", "password": "a-decent-password"})
    assert res.status_code == 201 and res.json()["user"]["email"] == "mixed.case@example.com"

    assert anon_client.post(
        "/api/auth/register", json={"email": "MIXED.CASE@example.COM", "password": "a-decent-password"}
    ).status_code == 409
    assert _login(anon_client, "MIXED.case@EXAMPLE.com", "a-decent-password").status_code == 200


# ---------------------------------------------------------------------------
# Google sign-in must not take over an existing password account
# ---------------------------------------------------------------------------

def _google_profile(monkeypatch, *, sub="google-sub-123", email="someone@example.com"):
    from backend.app.api.v1 import auth as auth_api
    from backend.app.auth.google_login import GoogleProfile

    monkeypatch.setattr(
        auth_api, "verify_google_id_token", lambda token: GoogleProfile(sub=sub, email=email, name="G", picture=None)
    )


def test_google_sign_in_creates_a_new_account_and_then_finds_it_by_sub(anon_client, monkeypatch):
    _google_profile(monkeypatch)
    first = anon_client.post("/api/auth/google", json={"id_token": "t"})
    second = anon_client.post("/api/auth/google", json={"id_token": "t"})

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]


def test_google_sign_in_refuses_to_link_onto_an_existing_password_account(anon_client, monkeypatch):
    """The pre-hijack scenario: an attacker registers victim@example.com with a password they know;
    when the real owner later signs in with Google, that must NOT attach Google to the attacker's
    account (which would leave the attacker's password working on the owner's account)."""
    attacker_account = make_user("victim@example.com")
    _google_profile(monkeypatch, sub="victims-real-google-sub", email="victim@example.com")

    res = anon_client.post("/api/auth/google", json={"id_token": "t"})

    assert res.status_code == 409 and "password" in res.json()["detail"].lower()
    with SessionLocal() as session:
        row = session.get(User, attacker_account.id)
        assert row.google_sub is None  # nothing was linked
        assert session.query(User).filter(User.email == "victim@example.com").count() == 1


def test_google_sign_in_matches_existing_email_case_insensitively_before_refusing(anon_client, monkeypatch):
    make_user("case@example.com")
    _google_profile(monkeypatch, sub="s", email="Case@Example.com")
    assert anon_client.post("/api/auth/google", json={"id_token": "t"}).status_code == 409
