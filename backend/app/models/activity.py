"""
models/activity.py — SQLAlchemy model for ActivityLog.

An append-only, per-user audit trail: one row per thing that *happened*
("task completed", "deadline pushed out by the replan", "calendar
connected"). It exists for two reasons:

1. Debugging in production -- "why didn't my schedule run / why is this
   task gone" is answerable from the database instead of from logs that
   may have rotated.
2. The "Why did BrainDUMP move this task?" feature (GET
   /api/tasks/{id}/history). The deterministic planner already knows
   *why* it does what it does; this table is where that reasoning is
   written down at the moment it happens, so the UI can show the real
   reason instead of asking an LLM to reconstruct one afterwards.

Rows are never updated (hence no TimestampMixin/updated_at) and are
pruned by age, not edited -- see services/workspace/activity_service.py
for the write path and the retention purge.

`entity_type` + `entity_id` point at the thing acted on ("task", 42) and
are deliberately NOT foreign keys: a project or task can be deleted and
its history should still read correctly ("Deleted project 'X'"), and an
FK would either block that delete or cascade the trail away with it.
Only `user_id` is an FK -- deleting a user takes their trail with them.

`details` is free-form JSON, sanitized (secrets dropped, sizes capped)
before it is stored -- see activity_service._sanitize().
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base
from backend.app.models.mixins import utcnow


class ActivityLog(Base):
    __tablename__ = "activity_log"
    __table_args__ = (
        # The activity feed: newest-first for one user, paged by id.
        Index("ix_activity_log_user_id_id", "user_id", "id"),
        # One entity's history ("everything that happened to task 42").
        Index("ix_activity_log_user_entity", "user_id", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Dotted "<noun>.<past-tense verb>", e.g. "task.completed". The full
    # vocabulary lives in activity_service.Action so call sites can't typo it.
    action: Mapped[str] = mapped_column(String(64), nullable=False)

    entity_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Who/what caused it: "user" (an explicit request), "system" (a
    # scheduled job), or "ai" (an LLM-driven flow such as a brain dump).
    actor: Mapped[str] = mapped_column(String(16), default="user", nullable=False)

    details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityLog id={self.id} user_id={self.user_id} action={self.action} "
            f"entity={self.entity_type}:{self.entity_id}>"
        )
