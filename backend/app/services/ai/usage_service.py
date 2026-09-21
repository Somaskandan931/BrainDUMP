"""
services/usage_service.py — per-user daily AI usage cap.

Called from ai/ollama_client.call_model() around every real OpenRouter
request: enforce_limit() first (raises AIUsageLimitExceeded once the
day's config.AI_DAILY_CALL_LIMIT is reached), record_call() after a
successful response.

Deliberately keyed on UTC calendar date, not a rolling 24h window --
simpler to reason about ("resets at midnight UTC") and matches the same
per-day convention ProductivityMetric/DailyPlan already use.
"""

from __future__ import annotations

from datetime import date as date_type, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.models.usage import UsageRecord


class AIUsageLimitExceeded(RuntimeError):
    """Raised by enforce_limit() when today's AI-call cap is reached.

    Subclasses nothing in ai/ollama_client on purpose (it's raised
    *before* any provider call is attempted, not a transport/content
    failure) -- callers that only `except OllamaError` won't catch this,
    so a usage-limit rejection surfaces distinctly (see api/planner.py's
    429 handling) rather than being mislabeled as "AI backend
    unavailable".
    """


def _today() -> date_type:
    return datetime.now(timezone.utc).date()


def _get_or_create(db: Session, user_id: int, day: date_type) -> UsageRecord:
    row = db.query(UsageRecord).filter(UsageRecord.user_id == user_id, UsageRecord.date == day).first()
    if row is None:
        row = UsageRecord(user_id=user_id, date=day)
        db.add(row)
        db.flush()
    return row


def calls_today(db: Session, user_id: int) -> int:
    row = db.query(UsageRecord).filter(
        UsageRecord.user_id == user_id, UsageRecord.date == _today()
    ).first()
    return row.ai_calls if row else 0


def enforce_limit(db: Session, user_id: int) -> None:
    """Raise AIUsageLimitExceeded if `user_id` has already used today's
    quota. config.AI_DAILY_CALL_LIMIT <= 0 means unlimited (no-op)."""
    limit = config.AI_DAILY_CALL_LIMIT
    if limit <= 0:
        return
    if calls_today(db, user_id) >= limit:
        raise AIUsageLimitExceeded(
            f"Daily AI usage limit reached ({limit} calls/day). Resets at midnight UTC."
        )


def record_call(
    db: Session, user_id: int, input_tokens: Optional[int] = None, output_tokens: Optional[int] = None
) -> UsageRecord:
    """Increment today's row for `user_id` by one call (+ token counts,
    when the caller has them). Commits -- called right after a
    successful provider response, independent of whatever the caller
    does with that response next."""
    row = _get_or_create(db, user_id, _today())
    row.ai_calls += 1
    row.input_tokens += input_tokens or 0
    row.output_tokens += output_tokens or 0
    db.commit()
    return row
