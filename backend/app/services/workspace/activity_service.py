"""
services/workspace/activity_service.py — write path, read path, and
retention for the per-user audit trail (models/activity.py).

Design rules, in the order they matter:

1. Auditing must never break the thing being audited. log_activity()
   catches its own failures and returns None -- a task still completes
   even if its audit row couldn't be built. (A database error at flush
   time is the one failure this can't intercept; it surfaces at the
   caller's commit exactly like any other write in the same transaction.)

2. log_activity() adds the row to the caller's session and does NOT
   commit. The audit row therefore lands in the same transaction as the
   change it describes: both persist or neither does, so the trail can't
   claim something happened that was rolled back, or miss something that
   stuck. Callers that have already committed their change call
   db.commit() once more after logging.

3. Nothing secret goes in `details`. Keys that look like credentials are
   dropped, strings/lists/nesting are capped, and an over-large payload
   is replaced by a stub -- see sanitize_details().

4. Raw user content stays out by default. Log ids, counts, field names
   and old/new values of small structured fields; don't copy a whole
   brain-dump text or task description into the trail.

The action vocabulary is the `Action` class below -- import the constant
rather than typing the string at a call site.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.db.database import owner_id
from backend.app.models.activity import ActivityLog

logger = logging.getLogger(__name__)


class Action:
    """Every action string the app writes. Convention: "<noun>.<past-tense verb>"."""

    # Planning / AI
    BRAIN_DUMP_PROCESSED = "brain_dump.processed"
    GOAL_PLAN_GENERATED = "goal.plan_generated"

    # Projects
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_COMPLETED = "project.completed"
    PROJECT_DELETED = "project.deleted"

    # Tasks
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_ARCHIVED = "task.archived"
    TASK_COMPLETED = "task.completed"
    TASK_SKIPPED = "task.skipped"
    # A deadline the *planner* moved (as opposed to one the user edited,
    # which is a task.updated with a deadline entry in `changes`).
    TASK_DEADLINE_CHANGED = "task.deadline_changed"

    # Schedule
    SCHEDULE_REPLANNED = "schedule.replanned"
    SCHEDULE_DAY_STARTED = "schedule.day_started"

    # Calendar
    CALENDAR_CONNECTED = "calendar.connected"
    CALENDAR_DISCONNECTED = "calendar.disconnected"

    # Account security
    AUTH_REGISTERED = "auth.registered"
    AUTH_EMAIL_VERIFIED = "auth.email_verified"
    AUTH_PASSWORD_RESET = "auth.password_reset"


ACTOR_USER = "user"
ACTOR_SYSTEM = "system"
ACTOR_AI = "ai"
_ACTORS = frozenset({ACTOR_USER, ACTOR_SYSTEM, ACTOR_AI})

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# ---------------------------------------------------------------------------
# Sanitizing `details`
# ---------------------------------------------------------------------------

# Any dict key containing one of these (case-insensitive) is dropped, at any
# depth. Deliberately a substring match: "reset_token", "google_refresh_token"
# and "Authorization" should all vanish without anyone remembering to list them.
_SECRET_KEY_MARKERS = ("password", "passwd", "token", "secret", "credential", "authorization", "api_key", "apikey")

_MAX_STRING_CHARS = 500
_MAX_COLLECTION_ITEMS = 50
_MAX_DEPTH = 4
_MAX_SERIALIZED_BYTES = 4096


def _is_secret_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def _jsonable(value: Any, depth: int = 0) -> Any:
    """Coerce `value` into something the JSON column can always store."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None  # NaN/inf aren't valid JSON
    if isinstance(value, Enum):
        return _jsonable(value.value, depth)
    if isinstance(value, datetime):
        # SQLite returns naive datetimes; everything in this app is UTC, and a
        # timezone-less ISO string would be read as *local* time by a browser.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING_CHARS else value[: _MAX_STRING_CHARS - 1] + "…"
    if depth >= _MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:_MAX_COLLECTION_ITEMS]:
            if _is_secret_key(key):
                continue
            out[str(key)] = _jsonable(item, depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)[:_MAX_COLLECTION_ITEMS]
        return [_jsonable(item, depth + 1) for item in items]
    return _jsonable(str(value), depth)


def sanitize_details(details: Optional[dict]) -> Optional[dict]:
    """Return a JSON-safe, size-bounded, secret-free copy of `details`
    (or None if there's nothing to store)."""
    if not details:
        return None
    cleaned = _jsonable(dict(details))
    if not cleaned:
        return None
    if len(json.dumps(cleaned, default=str)) > _MAX_SERIALIZED_BYTES:
        return {"truncated": True, "keys": sorted(cleaned)[:20]}
    return cleaned


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


def log_activity(
    db: Session,
    action: str,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
    actor: str = ACTOR_USER,
    user_id: Optional[int] = None,
) -> Optional[ActivityLog]:
    """Stage one audit row on `db` (no commit -- see the module docstring).

    `user_id` defaults to the session's scoped user. Pass it explicitly
    only where there is no scoped session yet (the auth routes, which
    run before a user is known to the tenant filter).

    Returns the staged row, or None if it couldn't be recorded (bad
    arguments, no user to attribute it to, or an unexpected error) --
    always logged, never raised.
    """
    try:
        if not action or len(action) > 64:
            logger.warning("activity: refusing to log an empty or over-long action %r", action)
            return None
        if actor not in _ACTORS:
            logger.warning("activity: unknown actor %r for action %s", actor, action)
            return None

        resolved_user_id = user_id if user_id is not None else db.info.get("user_id")
        if resolved_user_id is None:
            logger.warning("activity: no user to attribute %s to (unscoped session, no user_id)", action)
            return None

        row = ActivityLog(
            user_id=resolved_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            details=sanitize_details(details),
        )
        db.add(row)
        return row
    except Exception:  # noqa: BLE001 - auditing must never break the audited operation
        logger.exception("activity: failed to record %s", action)
        return None


def _comparable(value: Any) -> Any:
    """Normalize a value for old-vs-new comparison. SQLite hands datetimes
    back naive while request payloads are timezone-aware; treating naive as
    UTC stops a no-op edit from being logged as a change."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def diff_changes(obj: Any, changes: dict, tracked: Iterable[str]) -> dict:
    """Describe what applying `changes` (field -> new value) to `obj`
    would actually change. Call BEFORE setattr-ing the changes.

    Returns {} when nothing differs (so a no-op PUT logs nothing), else:
      {"changes": {field: {"from": old, "to": new}}}   for `tracked` fields
      {"other_fields": [names]}                         for the rest --
    names only, because free-text fields (descriptions, notes) are the
    "raw user content" the trail deliberately doesn't copy.
    """
    tracked = set(tracked)
    tracked_changes: dict = {}
    other_fields: List[str] = []
    for field, new_value in changes.items():
        old_value = getattr(obj, field, None)
        if _comparable(old_value) == _comparable(new_value):
            continue
        if field in tracked:
            tracked_changes[field] = {"from": old_value, "to": new_value}
        else:
            other_fields.append(field)

    result: dict = {}
    if tracked_changes:
        result["changes"] = tracked_changes
    if other_fields:
        result["other_fields"] = sorted(other_fields)
    return result


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


def list_activity(
    db: Session,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = DEFAULT_PAGE_SIZE,
    before_id: Optional[int] = None,
) -> Tuple[List[ActivityLog], Optional[int]]:
    """The caller's activity, newest first. Returns (rows, next_cursor),
    where next_cursor is the `before_id` to pass for the next page (None
    on the last page). Paged by id, not offset, so rows arriving while
    someone scrolls don't shift the page under them.

    Filters on the scoped user explicitly, on top of the tenant listener
    -- owner_id() also makes an accidental unscoped call fail loudly
    instead of returning everyone's history.
    """
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    query = db.query(ActivityLog).filter(ActivityLog.user_id == owner_id(db))
    if entity_type is not None:
        query = query.filter(ActivityLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(ActivityLog.entity_id == entity_id)
    if action is not None:
        query = query.filter(ActivityLog.action == action)
    if before_id is not None:
        query = query.filter(ActivityLog.id < before_id)

    rows = query.order_by(ActivityLog.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return rows, (rows[-1].id if has_more and rows else None)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def purge_older_than(db: Session, days: int) -> int:
    """Delete the scoped user's activity older than `days` days; returns
    the number of rows removed. days <= 0 disables purging (keep
    everything). Does not commit -- the caller owns the transaction.

    Run per user from the nightly job (which scopes its session one user
    at a time), so the trail is bounded without a cross-tenant sweep.
    """
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == owner_id(db), ActivityLog.created_at < cutoff)
        .delete(synchronize_session=False)
    )
