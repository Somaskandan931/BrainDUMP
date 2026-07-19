"""
models/calendar_event.py — SQLAlchemy model for CalendarEvent.

Serves two purposes:
1. Local cache of Google Calendar events (source=GOOGLE) so the
   scheduler can compute free/busy without hitting the API on every
   planning run.
2. Work-session blocks the scheduler itself creates and pushes to
   Google Calendar (source=BRAIN_DUMP), task_id set, synced tracks
   whether the push succeeded.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import EventSource, SyncStatus, sa_enum
from backend.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.models.task import Task
    from backend.models.session import WorkSession


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Null for events not tied to a Brain Dump task (e.g. imported "College" block).
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )

    # External Google Calendar event id — used to reconcile on sync. Unique
    # when present; null for events that haven't been pushed/pulled yet.
    google_event_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped[EventSource] = mapped_column(
        sa_enum(EventSource), default=EventSource.BRAIN_DUMP, nullable=False
    )
    sync_status: Mapped[SyncStatus] = mapped_column(
        sa_enum(SyncStatus), default=SyncStatus.NOT_SYNCED, nullable=False
    )
    synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task: Mapped[Optional["Task"]] = relationship(back_populates="calendar_events")
    sessions: Mapped[List["WorkSession"]] = relationship(back_populates="calendar_event")

    def __repr__(self) -> str:
        return f"<CalendarEvent id={self.id} title={self.title!r} start={self.start_time}>"
