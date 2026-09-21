"""
models/activity.py — SQLAlchemy model for ActivityLog.

One row per meaningful thing that happened to a user's data: a task
created, a deadline pushed by the planner, a project deleted, a
calendar connected. Backs GET /api/activity/ (the activity feed) and
GET /api/tasks/{id}/history (the "why did BrainDUMP move this task?"
feature) -- see services/workspace/activity_service.py for how rows
are written and read.

Design notes:
- entity_id/entity_type is deliberately NOT a foreign key. A task or
  project can be deleted; its history should still read correctly
  afterwards instead of cascading away or dangling on a broken FK.
- `details` is a small JSON blob (old/new values, a planner's reasoning
  for a deadline move, etc.) -- activity_service.log_activity() caps its
  size and strips secret-looking keys before it ever reaches this
  column, so nothing here should be treated as validated/trusted input.
- `actor` distinguishes a row the user caused directly from one a
  background job or the AI caused on their behalf (nightly replan,
  Todoist-triggered completion, brain-dump task creation).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base
from backend.app.models.mixins import TimestampMixin


class ActivityLog(Base, TimestampMixin):
    __tablename__ = "activity_log"
    __table_args__ = (
        # The activity feed's dominant query (list_activity() in
        # activity_service.py): a user's rows newest-first. Must match the
        # index created by migrations/versions/0009_add_activity_log.py --
        # tests/unit/test_migrations.py::test_migrations_match_the_models
        # guards the two staying in sync.
        Index("ix_activity_log_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # e.g. "task.created", "task.deadline_pushed", "project.deleted",
    # "schedule.replanned", "calendar.connected", "auth.password_reset".
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # e.g. "task" / 42. No FK -- see module docstring.
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # "user" (the person did it), "system" (a background job did it),
    # or "ai" (a brain-dump/goal-planning call created it).
    actor: Mapped[str] = mapped_column(String(20), nullable=False, default="user")

    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} user_id={self.user_id} action={self.action!r}>"
