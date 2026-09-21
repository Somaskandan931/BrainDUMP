"""
core/redis_client.py — one cached Redis connection per process, shared by
everything that wants cross-instance coordination when config.REDIS_URL is
set: auth/rate_limit.py's RedisSlidingWindowLimiter and
jobs/distributed_lock.py's job_lock(). Kept as a single module so both
consumers reuse one connection pool instead of opening their own, and so
"Redis is configured but unreachable" is detected and logged exactly once
per process rather than once per feature.
"""

from __future__ import annotations

import logging

from backend.app.core import config

logger = logging.getLogger(__name__)

_client = None
_unavailable = False


def get_redis_client():
    """Lazily creates and caches one Redis client for the process.

    Only meaningful when config.REDIS_URL is set -- callers should check
    that themselves before calling this (it doesn't check for them, so a
    caller with its own "no REDIS_URL => skip entirely" branch doesn't pay
    for the check twice). If the connection fails (Redis down, wrong URL,
    `redis` package missing), this logs once and returns None; callers are
    expected to fall back to their non-Redis behavior rather than raise --
    a misconfigured/unreachable Redis should degrade a feature (rate
    limiting, job coordination), not take the app down.
    """
    global _client, _unavailable
    if _client is not None or _unavailable:
        return _client
    try:
        import redis as redis_lib

        client = redis_lib.from_url(config.REDIS_URL, decode_responses=False, socket_timeout=2)
        client.ping()
        _client = client
        return _client
    except Exception:
        logger.exception(
            "REDIS_URL is set but Redis is unreachable; Redis-dependent "
            "features (rate limiting, job locking) are falling back to "
            "their single-process behavior for this process."
        )
        _unavailable = True
        return None


def reset_for_tests() -> None:
    """Test-only: clears the cached client/unavailable flag so a test can
    monkeypatch config.REDIS_URL and re-exercise the connect path."""
    global _client, _unavailable
    _client = None
    _unavailable = False
