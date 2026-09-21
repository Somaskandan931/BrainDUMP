"""
auth/rate_limit.py — small in-memory sliding-window limiter for the auth
endpoints (login / register / Google sign-in), so /api/auth/login can't be
brute-forced.

Deliberately dependency-free and per-process: state lives in this
process's memory, so it resets on restart and isn't shared between
workers/instances. That is the right size for this app (one API process,
SQLite) and still stops the realistic attack -- an online password guess
loop against one instance. A multi-instance deployment would swap this for
a shared store (Redis), keeping the same `blocked_for()/hit()/reset()`
surface.

Policy (numbers in config.py) is applied in api/auth.py:
- login: failures are counted per (client IP, email) -- so a stranger
  hammering an account can't lock its real owner out from their own IP --
  and per client IP overall, which stops one machine spraying many emails.
  Unknown emails count exactly like wrong passwords, so a 429 doesn't reveal
  whether an account exists.
- register / Google sign-in: attempts per client IP.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional

# Hard cap on distinct tracked keys so a flood of unique emails/IPs can't grow
# memory without bound; when hit, expired keys are dropped first, then oldest.
_MAX_KEYS = 20_000


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


def retry_after_message(seconds: int) -> str:
    minutes = math.ceil(seconds / 60)
    wait = f"{minutes} minute{'s' if minutes != 1 else ''}" if seconds >= 60 else f"{seconds} seconds"
    return f"Too many attempts. Try again in {wait}."
