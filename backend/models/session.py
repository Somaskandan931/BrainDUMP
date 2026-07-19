"""
models/session.py — SQLAlchemy model for WorkSession (focus/timer sessions).

Created when the user hits "Start Timer" on the Next Best Task, or
retroactively when logging completed work. This is the ground truth
table that ml/estimator.py trains on: predicted_duration_minutes vs.
the actual elapsed time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.models.task import Task
    from backend.models.calendar_event import CalendarEvent


class WorkSession(Base, TimestampMixin):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Optional link back to the calendar block this session was scheduled in.
    calendar_event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="SET NULL"), nullable=True
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    predicted_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="sessions")
    calendar_event: Mapped[Optional["CalendarEvent"]] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        return f"<WorkSession id={self.id} task_id={self.task_id} start={self.start_time}>"
