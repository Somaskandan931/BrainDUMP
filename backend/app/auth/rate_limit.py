"""
auth/rate_limit.py — sliding-window limiter for the auth endpoints
(login / register / Google sign-in / email actions), so /api/auth/* can't
be brute-forced.

Two implementations share one interface (`blocked_for()/hit()/reset()/clear()`),
so api/v1/auth.py never has to know which one it's talking to:

- SlidingWindowLimiter: in-memory, per-process. Dependency-free, zero
  setup, and the right size for a single API process (state resets on
  restart, isn't shared between workers/instances). Still stops the
  realistic single-instance attack -- an online password guess loop.
- RedisSlidingWindowLimiter: same semantics, backed by Redis sorted sets,
  for when more than one API process/instance is running. Without this,
  each process has its own counters and the real limit silently
  multiplies by the instance count -- e.g. 5 processes behind a load
  balancer effectively allow 25 login failures, not 5.

get_limiter() below picks one based on config.REDIS_URL, so call sites
just construct through the factory and don't care which backend they got.

Policy (numbers in config.py) is applied in api/v1/auth.py:
- login: failures are counted per (client IP, email) -- so a stranger
  hammering an account can't lock its real owner out from their own IP --
  and per client IP overall, which stops one machine spraying many emails.
  Unknown emails count exactly like wrong passwords, so a 429 doesn't reveal
  whether an account exists.
- register / Google sign-in / email actions: attempts per client IP.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections import deque
from typing import Callable, Deque, Dict, Optional, Protocol

from backend.app.core import config

# Hard cap on distinct tracked keys so a flood of unique emails/IPs can't grow
# memory without bound; when hit, expired keys are dropped first, then oldest.
_MAX_KEYS = 20_000


class Limiter(Protocol):
    """Shared surface both backends implement -- see module docstring."""

    def blocked_for(self, key: str) -> Optional[int]: ...
    def hit(self, key: str) -> None: ...
    def reset(self, key: str) -> None: ...
    def clear(self) -> None: ...


class SlidingWindowLimiter:
    def __init__(
        self, max_events: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Optional[Deque[float]]:
        events = self._events.get(key)
        if events is None:
            return None
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            del self._events[key]
            return None
        return events

    def blocked_for(self, key: str) -> Optional[int]:
        """Whole seconds until `key` may try again, or None if it isn't limited."""
        with self._lock:
            now = self._clock()
            events = self._prune(key, now)
            if events is None or len(events) < self.max_events:
                return None
            return max(1, math.ceil(events[0] + self.window_seconds - now))

    def hit(self, key: str) -> None:
        """Record one event (a failed login, a registration attempt, ...) for `key`."""
        with self._lock:
            now = self._clock()
            if key not in self._events and len(self._events) >= _MAX_KEYS:
                self._evict(now)
            self._events.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def _evict(self, now: float) -> None:
        for k in list(self._events):
            self._prune(k, now)
        while len(self._events) >= _MAX_KEYS:
            self._events.pop(next(iter(self._events)))  # oldest-inserted


class RedisSlidingWindowLimiter:
    """Same sliding-window semantics as SlidingWindowLimiter, shared across
    every process/instance via one Redis sorted set per key.

    Each event is stored as a zset member scored by its timestamp; a member
    needs to be unique even when two events land in the same millisecond
    (two failed logins from the same IP in one request-per-millisecond
    burst), so each entry is "<timestamp>:<random suffix>" rather than the
    bare timestamp. blocked_for() prunes expired members with ZREMRANGEBYSCORE
    before counting, so the set never grows unbounded even for a key that's
    hit but never re-checked; a TTL on the key is a second backstop for the
    same reason (a key that stops being touched cleans itself up instead of
    living in Redis forever).
    """

    _KEY_PREFIX = "ratelimit:"

    def __init__(self, max_events: int, window_seconds: float, redis_client) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._redis = redis_client

    def _rkey(self, key: str) -> str:
        return f"{self._KEY_PREFIX}{key}"

    def blocked_for(self, key: str) -> Optional[int]:
        rkey = self._rkey(key)
        now = time.time()
        cutoff = now - self.window_seconds
        self._redis.zremrangebyscore(rkey, "-inf", cutoff)
        count = self._redis.zcard(rkey)
        if count < self.max_events:
            return None
        oldest = self._redis.zrange(rkey, 0, 0, withscores=True)
        if not oldest:
            return None
        oldest_ts = oldest[0][1]
        return max(1, math.ceil(oldest_ts + self.window_seconds - now))

    def hit(self, key: str) -> None:
        rkey = self._rkey(key)
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe = self._redis.pipeline()
        pipe.zadd(rkey, {member: now})
        pipe.zremrangebyscore(rkey, "-inf", now - self.window_seconds)
        # A little slack past the window so a key that goes quiet still
        # expires from Redis on its own instead of lingering indefinitely.
        pipe.expire(rkey, math.ceil(self.window_seconds) + 60)
        pipe.execute()

    def reset(self, key: str) -> None:
        self._redis.delete(self._rkey(key))

    def clear(self) -> None:
        # Test/dev convenience only (mirrors SlidingWindowLimiter.clear()) --
        # SCAN so a large shared Redis isn't blocked by a single KEYS call.
        cursor = 0
        pattern = f"{self._KEY_PREFIX}*"
        while True:
            cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                self._redis.delete(*keys)
            if cursor == 0:
                break


_redis_client = None
_redis_unavailable = False


def _get_redis_client():
    """Delegates to core.redis_client.get_redis_client() (shared cache with
    jobs/distributed_lock.py -- see that module's docstring). Kept as a
    thin wrapper here so existing call sites/tests in this module don't
    need to change."""
    from backend.app.core.redis_client import get_redis_client

    return get_redis_client()


def get_limiter(max_events: int, window_seconds: float) -> Limiter:
    """Factory every call site in api/v1/auth.py should use instead of
    constructing SlidingWindowLimiter directly -- picks Redis when
    config.REDIS_URL is set and reachable, in-memory otherwise."""
    if config.REDIS_URL:
        client = _get_redis_client()
        if client is not None:
            return RedisSlidingWindowLimiter(max_events, window_seconds, client)
    return SlidingWindowLimiter(max_events, window_seconds)


def retry_after_message(seconds: int) -> str:
    minutes = math.ceil(seconds / 60)
    wait = f"{minutes} minute{'s' if minutes != 1 else ''}" if seconds >= 60 else f"{seconds} seconds"
    return f"Too many attempts. Try again in {wait}."
