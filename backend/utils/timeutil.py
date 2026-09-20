"""
utils/timeutil.py — timezone helpers.

SQLite has no native tz-aware datetime type. SQLAlchemy's
DateTime(timezone=True) columns accept aware datetimes fine going in,
but the stock sqlite3 DBAPI drops the UTC offset coming back out, so
ORM reads silently hand back a *naive* datetime that actually
represents UTC (see services/scheduler_service.py::_as_utc for the
same issue on the read side of scheduling).

If that naive value is serialized straight to JSON, it comes out as
e.g. "2026-07-20T06:14:00" with no 'Z'/offset — and `new Date(...)` in
the browser reads a bare ISO string like that as *local* time, not
UTC. The visible symptom is every timestamp in the UI silently
shifting by the browser's UTC offset (IST: displayed ~5.5h behind the
real time). ensure_utc() re-attaches UTC before a datetime ever leaves
the API, which is the one place this needs fixing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Attach UTC if naive, convert if aware-but-not-UTC. Every datetime
    this app writes is UTC in practice (models/mixins.py::utcnow(),
    calendar_sync_service.py) — this just guarantees the value leaving
    the API says so explicitly, so any client parses it correctly."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
