"""
services/workspace/activity_service.py — audit trail / task-history backend.

log_activity() is called from every route/job that changes user-owned
data (see the call sites in api/v1/tasks.py, projects.py, planner.py,
schedule.py, calendar.py, auth.py, and jobs/tasks/*.py). It:

- Never raises. A logging failure should never break the request it's
  logging -- it's caught and swallowed (with a log line) rather than
  turned into a 500 for an otherwise-successful task update.
- Adds the row to the CALLER's transaction without committing. The
  caller commits once, after making its real change, so the audit row
  and the change it describes always land together or not at all --
  there is never a committed data change with no matching log row, or
  a log row for a change that then rolled back.
- Strips anything that looks like a secret and caps the size of
  `details`, since `details` often carries a caller-supplied dict that
  may include more than was intended for a permanent log.

list_activity() and get_entity_history() back the two read endpoints
(api/v1/activity.py): the account-wide feed and a single task's/
project's history respectively. Both are cursor-paged on `id` (stable
under concurrent inserts, unlike an offset).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.app.models.activity import ActivityLog

logger = logging.getLogger(__name__)

_MAX_DETAILS_KEYS = 20
_MAX_STRING_LEN = 500
_SECRET_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "refresh",
    "access_token",
    "hashed",
    "api_key",
    "apikey",
    "authorization",
    "raw_text",  # brain-dump/goal free text -- not a secret, but not audit content either
    "brain_dump",
    "goal_text",
)


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_STRING_LEN:
        return value[:_MAX_STRING_LEN] + "…"
    if isinstance(value, dict):
        return _sanitize_details(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in list(value)[:_MAX_DETAILS_KEYS]]
    return value


def _sanitize_details(details: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not details:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if _looks_secret(key):
            continue
        cleaned[key] = _sanitize_value(value)
        if len(cleaned) >= _MAX_DETAILS_KEYS:
            break
    return cleaned or None


def diff_changes(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """{"field": {"old": ..., "new": ...}} for every key whose value
    actually changed. Used by update hooks so a no-op PUT (every field
    resubmitted unchanged) logs nothing -- see the callers in
    api/v1/tasks.py / projects.py, which skip log_activity() entirely
    when this returns {}."""
    changed: dict[str, Any] = {}
    for key, new_value in new.items():
        old_value = old.get(key)
        if old_value != new_value:
            changed[key] = {"old": old_value, "new": new_value}
    return changed


def log_activity(
    db: Session,
    *,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    actor: str = "user",
    details: Optional[dict[str, Any]] = None,
) -> None:
    try:
        row = ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            details=_sanitize_details(details),
        )
        db.add(row)
        # Deliberately no db.commit() here -- see module docstring.
    except Exception:  # noqa: BLE001 -- logging must never break the caller's real work
        logger.exception("activity_service: failed to log %s for user %s", action, user_id)


def list_activity(
    db: Session,
    *,
    user_id: int,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    cursor: Optional[int] = None,
    limit: int = 50,
) -> list[ActivityLog]:
    query = db.query(ActivityLog).filter(ActivityLog.user_id == user_id)
    if entity_type is not None:
        query = query.filter(ActivityLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(ActivityLog.entity_id == entity_id)
    if action is not None:
        query = query.filter(ActivityLog.action == action)
    if cursor is not None:
        query = query.filter(ActivityLog.id < cursor)
    return query.order_by(ActivityLog.id.desc()).limit(min(limit, 200)).all()


def get_entity_history(
    db: Session, *, user_id: int, entity_type: str, entity_id: int, limit: int = 100
) -> list[ActivityLog]:
    return list_activity(db, user_id=user_id, entity_type=entity_type, entity_id=entity_id, limit=limit)


def purge_older_than(db: Session, *, user_id: int, days: int) -> int:
    """Deletes this user's rows older than `days`. days<=0 is a no-op (keep
    everything) -- see config.ACTIVITY_LOG_RETENTION_DAYS, applied per-user
    from the nightly job (jobs/tasks/nightly_replan.py)."""
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = (
        db.query(ActivityLog)
        .filter(and_(ActivityLog.user_id == user_id, ActivityLog.created_at < cutoff))
        .delete(synchronize_session=False)
    )
    return deleted
