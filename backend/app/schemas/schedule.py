"""
schemas/schedule.py — Pydantic schemas for the Today schedule lock
(backend/models/daily_plan.py, backend/services/schedule_service.py).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# The six buffer presets the Today dashboard's slider snaps to. Kept
# here (not just in the frontend) so StartDayRequest can validate
# against the same set the UI offers — an arbitrary multiplier from a
# stray API call shouldn't silently become the day's buffer setting.
BUFFER_MULTIPLIERS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75)


class StartDayRequest(BaseModel):
    buffer_multiplier: float = Field(default=1.0)


class DailyPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_date: date
    buffer_multiplier: float
    started_at: Optional[datetime]

    # schedule_service.start_day() always writes datetime.now(timezone.utc),
    # but SQLite has no native tz-aware storage: DateTime(timezone=True) is
    # silently downgraded, and db.refresh(plan) reads started_at back as a
    # *naive* datetime. Serialized as-is, that naive value reaches the
    # frontend without a 'Z'/offset, and `new Date(...)` in the browser
    # parses a timezone-less ISO string as local time rather than UTC —
    # shifting the Today dashboard's countdown/overdue math by however far
    # the browser's timezone sits from UTC. Since we know every value in
    # this column originated as UTC, re-attach that tzinfo before it's
    # serialized, so the JSON response always carries an explicit offset.
    @field_validator("started_at")
    @classmethod
    def _ensure_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @computed_field  # type: ignore[misc]
    @property
    def locked(self) -> bool:
        return self.started_at is not None