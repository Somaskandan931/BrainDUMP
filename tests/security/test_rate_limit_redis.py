"""
Redis-backed sliding-window limiter (backend/app/auth/rate_limit.py).

Uses fakeredis's real-command sorted-set implementation so these assert
against actual ZADD/ZREMRANGEBYSCORE/ZRANGE behavior, not a hand-rolled
mock -- the same coverage test_auth.py already has for the in-memory
limiter, run here against RedisSlidingWindowLimiter to prove the two
backends agree on semantics. Also covers get_limiter()'s fallback when
Redis is configured but unreachable, since that degrade path is the one
place a misconfiguration could silently take auth down instead of just
losing cross-instance sharing.
"""

from __future__ import annotations

import time

import fakeredis
import pytest

from backend.app.auth import rate_limit
from backend.app.auth.rate_limit import RedisSlidingWindowLimiter, SlidingWindowLimiter, get_limiter


@pytest.fixture
def fake_client():
    return fakeredis.FakeStrictRedis()


def test_redis_limiter_allows_up_to_max_events(fake_client):
    limiter = RedisSlidingWindowLimiter(max_events=3, window_seconds=60, redis_client=fake_client)
    for _ in range(3):
        assert limiter.blocked_for("k") is None
        limiter.hit("k")
    assert limiter.blocked_for("k") is not None


def test_redis_limiter_blocks_after_max_events(fake_client):
    limiter = RedisSlidingWindowLimiter(max_events=2, window_seconds=60, redis_client=fake_client)
    limiter.hit("k")
    limiter.hit("k")
    wait = limiter.blocked_for("k")
    assert wait is not None and wait > 0


def test_redis_limiter_window_expiry(fake_client):
    # Fake a slow clock by using a tiny window and sleeping past it --
    # exercises the real ZREMRANGEBYSCORE pruning path, not a mocked one.
    limiter = RedisSlidingWindowLimiter(max_events=1, window_seconds=0.2, redis_client=fake_client)
    limiter.hit("k")
    assert limiter.blocked_for("k") is not None
    time.sleep(0.3)
    assert limiter.blocked_for("k") is None


def test_redis_limiter_keys_are_independent(fake_client):
    limiter = RedisSlidingWindowLimiter(max_events=1, window_seconds=60, redis_client=fake_client)
    limiter.hit("account:a@example.com")
    assert limiter.blocked_for("account:a@example.com") is not None
    assert limiter.blocked_for("account:b@example.com") is None


def test_redis_limiter_reset_clears_one_key(fake_client):
    limiter = RedisSlidingWindowLimiter(max_events=1, window_seconds=60, redis_client=fake_client)
    limiter.hit("a")
    limiter.hit("b")
    limiter.reset("a")
    assert limiter.blocked_for("a") is None
    assert limiter.blocked_for("b") is not None


def test_redis_limiter_clear_removes_all_ratelimit_keys(fake_client):
    limiter = RedisSlidingWindowLimiter(max_events=1, window_seconds=60, redis_client=fake_client)
    limiter.hit("a")
    limiter.hit("b")
    limiter.clear()
    assert limiter.blocked_for("a") is None
    assert limiter.blocked_for("b") is None


def test_redis_limiter_sets_a_ttl_so_idle_keys_expire(fake_client):
    limiter = RedisSlidingWindowLimiter(max_events=5, window_seconds=60, redis_client=fake_client)
    limiter.hit("k")
    ttl = fake_client.ttl(limiter._rkey("k"))
    assert 0 < ttl <= 120


# ---------------------------------------------------------------------------
# get_limiter() factory: picks Redis when configured+reachable, falls back
# to in-memory when REDIS_URL is unset or the connection fails.
# ---------------------------------------------------------------------------


def test_get_limiter_defaults_to_in_memory_when_redis_url_unset(monkeypatch):
    monkeypatch.setattr(rate_limit.config, "REDIS_URL", "", raising=False)
    limiter = get_limiter(5, 60)
    assert isinstance(limiter, SlidingWindowLimiter)


def test_get_limiter_uses_redis_when_configured_and_reachable(monkeypatch):
    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(rate_limit.config, "REDIS_URL", "redis://fake:6379/0", raising=False)
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: fake)
    limiter = get_limiter(5, 60)
    assert isinstance(limiter, RedisSlidingWindowLimiter)


def test_get_limiter_falls_back_when_redis_unreachable(monkeypatch):
    # A configured-but-dead Redis should degrade to in-memory, not raise --
    # a Redis outage shouldn't take auth down with it.
    monkeypatch.setattr(rate_limit.config, "REDIS_URL", "redis://unreachable:6379/0", raising=False)
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: None)
    limiter = get_limiter(5, 60)
    assert isinstance(limiter, SlidingWindowLimiter)
