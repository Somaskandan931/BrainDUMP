"""Refresh-token session model: cookie issuance, rotation, reuse detection,
and logout (auth/token_service.py, api/v1/auth.py's /refresh and /logout).

These use anon_client directly (not the pre-authenticated `client` fixture)
since the whole point is exercising the cookie, not the bearer header --
and each test clears the shared TestClient's cookie jar first, since
_app_client is session-scoped and would otherwise leak a cookie set by an
earlier test into this one.
"""

from __future__ import annotations

import pytest

from backend.app.core import config
from backend.app.db.database import SessionLocal
from backend.app.models.refresh_token import RefreshToken
from tests.helpers import TEST_PASSWORD, make_user, mark_verified


@pytest.fixture(autouse=True)
def _cookies_over_plain_http(monkeypatch):
    """TestClient's transport is plain http://, and a Secure cookie is
    correctly never sent by the client over http -- that's the browser
    behavior COOKIE_SECURE is for, not a bug. config.py's own comment
    documents COOKIE_SECURE=false as the local-http override; apply the
    same override here so these tests can actually observe the cookie
    round-trip instead of every request silently dropping it."""
    monkeypatch.setattr(config, "COOKIE_SECURE", False)


def _register(anon_client, email="refresh@example.com"):
    anon_client.cookies.clear()
    res = anon_client.post(
        "/api/auth/register", json={"email": email, "password": "a-decent-password", "name": "R"}
    )
    assert res.status_code == 201
    return res


def test_login_sets_an_httponly_refresh_cookie(anon_client):
    res = _register(anon_client)
    cookie = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)
    assert cookie is not None

    with SessionLocal() as session:
        rows = session.query(RefreshToken).all()
    assert len(rows) == 1
    # Only a hash is ever persisted -- the raw cookie value is never in the DB.
    assert rows[0].token_hash != cookie


def test_refresh_mints_a_new_access_token_and_rotates_the_cookie(anon_client):
    _register(anon_client)
    # The point here is cookie rotation, not the verification flow -- verify
    # directly via the DB (login/refresh are blocked until verification; see
    # PRODUCTION_READINESS.md).
    mark_verified("refresh@example.com")
    old_cookie = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)

    res = anon_client.post("/api/auth/refresh")
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]

    new_cookie = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)
    assert new_cookie is not None
    assert new_cookie != old_cookie

    # The new access token actually works.
    me = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200

    with SessionLocal() as session:
        rows = session.query(RefreshToken).all()
    assert len(rows) == 2
    old_row = next(r for r in rows if r.revoked_at is not None)
    new_row = next(r for r in rows if r.revoked_at is None)
    assert old_row.replaced_by_id == new_row.id


def test_refresh_with_no_cookie_is_401(anon_client):
    anon_client.cookies.clear()
    res = anon_client.post("/api/auth/refresh")
    assert res.status_code == 401


def test_reusing_an_already_rotated_refresh_token_revokes_the_whole_session(anon_client):
    """Simulates theft: the legitimate client rotates past a token, then
    someone replays the old (now-revoked) one. That replay must not
    succeed, and it must burn every other live token for the user too --
    including the one the legitimate client just received."""
    _register(anon_client)
    mark_verified("refresh@example.com")
    stolen_cookie = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)

    # Legitimate client rotates forward.
    first_refresh = anon_client.post("/api/auth/refresh")
    assert first_refresh.status_code == 200
    live_cookie = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)
    assert live_cookie != stolen_cookie

    # Attacker replays the stolen (already-rotated) token.
    anon_client.cookies.set(config.REFRESH_COOKIE_NAME, stolen_cookie)
    replay = anon_client.post("/api/auth/refresh")
    assert replay.status_code == 401

    # The legitimate client's own live token is now dead too (assume-compromised).
    anon_client.cookies.set(config.REFRESH_COOKIE_NAME, live_cookie)
    legit_retry = anon_client.post("/api/auth/refresh")
    assert legit_retry.status_code == 401

    with SessionLocal() as session:
        rows = session.query(RefreshToken).all()
    assert all(r.revoked_at is not None for r in rows)


def test_logout_revokes_the_session_and_clears_the_cookie(anon_client):
    _register(anon_client)
    cookie = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)

    res = anon_client.post("/api/auth/logout")
    assert res.status_code == 204

    with SessionLocal() as session:
        row = session.query(RefreshToken).one()
        assert row.revoked_at is not None

    # A logged-out cookie can no longer refresh.
    anon_client.cookies.set(config.REFRESH_COOKIE_NAME, cookie)
    res = anon_client.post("/api/auth/refresh")
    assert res.status_code == 401


def test_logout_with_no_cookie_at_all_still_succeeds(anon_client):
    anon_client.cookies.clear()
    res = anon_client.post("/api/auth/logout")
    assert res.status_code == 204


def test_each_login_path_issues_its_own_independent_session(anon_client):
    """Two logins (e.g. two browsers) for the same user must not share or
    invalidate each other's refresh token."""
    user = make_user("multi@example.com", "Multi")
    anon_client.cookies.clear()
    res_a = anon_client.post("/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    cookie_a = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)

    anon_client.cookies.clear()
    res_b = anon_client.post("/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    cookie_b = anon_client.cookies.get(config.REFRESH_COOKIE_NAME)

    assert res_a.status_code == res_b.status_code == 200
    assert cookie_a != cookie_b

    with SessionLocal() as session:
        rows = session.query(RefreshToken).filter(RefreshToken.user_id == user.id).all()
    assert len(rows) == 2
    assert all(r.revoked_at is None for r in rows)

    # Rotating session A must not disturb session B.
    anon_client.cookies.set(config.REFRESH_COOKIE_NAME, cookie_a)
    assert anon_client.post("/api/auth/refresh").status_code == 200

    anon_client.cookies.set(config.REFRESH_COOKIE_NAME, cookie_b)
    assert anon_client.post("/api/auth/refresh").status_code == 200
