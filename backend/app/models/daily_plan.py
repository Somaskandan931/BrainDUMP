"""
models/daily_plan.py — SQLAlchemy model for DailyPlan.

Backs the "Start your day" lock on the Today dashboard: one row per
user per calendar date, holding the buffer multiplier the user picked on
the slider (services/deadline_service.BUFFER_MULTIPLIERS) and the moment
they hit "Start your day". Deliberately one field short of a full
scheduling engine — it doesn't snapshot task order, since sort_order on
Task already owns that and skipping/completing tasks after the day
starts should still reflect live state, not a frozen copy.

`started_at` is what makes a day "locked": null means the buffer slider
is still open and the schedule preview is computed from `datetime.now()`
on every read; once set, schedule_service anchors the Today schedule to
that timestamp instead, so times don't drift as the real clock moves
throughout the day.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.mixins import TimestampMixin


class DailyPlan(Base, TimestampMixin):
    __tablename__ = "daily_plans"
    # Was unique on plan_date alone (single-user); one plan per user per date now.
    __table_args__ = (UniqueConstraint("user_id", "plan_date", name="uq_daily_plans_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # In the server's local timezone (see services/schedule_service._today()
    # for why this isn't UTC).
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    buffer_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DailyPlan user_id={self.user_id} date={self.plan_date} "
            f"multiplier={self.buffer_multiplier} locked={self.started_at is not None}>"
        )
