"""
models/dependency.py — SQLAlchemy model for task Dependencies.

PRD §31/§62 (Database Design / Complete Database Schema) and the ERD in
§61 both specify a Dependency table (task_id, depends_on_task_id) so the
Scheduler Algorithm (§65) can build a dependency graph and topologically
sort tasks before packing them into slots — e.g. "Deployment" can't be
scheduled to finish before "Database" does. This table was previously
missing entirely; the scheduler had no way to express or respect
"task A can't start until task B is done".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.models.task import Task


class Dependency(Base, TimestampMixin):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_dependency_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # `task_id` cannot proceed/complete until `depends_on_task_id` is done.
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    depends_on_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    task: Mapped["Task"] = relationship(foreign_keys=[task_id])
    depends_on: Mapped["Task"] = relationship(foreign_keys=[depends_on_task_id])

    def __repr__(self) -> str:
        return f"<Dependency task_id={self.task_id} depends_on_task_id={self.depends_on_task_id}>"
