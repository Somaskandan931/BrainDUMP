"""
models/task.py — SQLAlchemy models for Task and Subtask.

Task is the central entity in the system. Most AI/ML output lands on a
Task row: estimated_hours + confidence_score come from the Estimator
Agent / ml/estimator.py, priority_score comes from ml/priority_model.py,
and status/completed_at get updated as the user works.

Subtask is deliberately lightweight — it exists for AI Task Breakdown
output (e.g. "Build RAG chatbot" -> Research, Dataset, Embedding, ...)
and doesn't carry its own priority score; subtasks inherit urgency from
their parent Task.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, DateTime, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import TaskStatus, Importance, EnergyLevel, sa_enum
from backend.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.models.project import Project
    from backend.models.session import WorkSession
    from backend.models.calendar_event import CalendarEvent
    from backend.models.prediction import Prediction


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Nullable: a task doesn't have to belong to a project (e.g. a
    # one-off "Gym" or "Buy groceries" item from a brain dump).
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(
        sa_enum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    importance: Mapped[Importance] = mapped_column(
        sa_enum(Importance), default=Importance.MEDIUM, nullable=False
    )
    energy_requirement: Mapped[Optional[EnergyLevel]] = mapped_column(
        sa_enum(EnergyLevel), nullable=True
    )

    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- AI/ML-populated fields -------------------------------------------------
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0-1.0
    priority_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    context_switch_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Milestone 6: Todoist two-way sync -----------------------------------
    # Null for tasks that only ever existed in Brain Dump. Set the moment a
    # task is either pushed to Todoist or pulled in from it — see
    # services/todoist_sync_service.py. Unique so reconciliation can't
    # accidentally double-link two local tasks to the same remote item.
    todoist_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (UniqueConstraint("todoist_id", name="uq_tasks_todoist_id"),)

    # --- Relationships ------------------------------------------------------
    project: Mapped[Optional["Project"]] = relationship(back_populates="tasks")
    subtasks: Mapped[List["Subtask"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    sessions: Mapped[List["WorkSession"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    calendar_events: Mapped[List["CalendarEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    predictions: Mapped[List["Prediction"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} status={self.status.value}>"


class Subtask(Base, TimestampMixin):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        sa_enum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )

    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="subtasks")

    def __repr__(self) -> str:
        return f"<Subtask id={self.id} title={self.title!r} status={self.status.value}>"
