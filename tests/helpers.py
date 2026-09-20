"""Small factories shared by the test modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.enums import Importance, TaskStatus
from backend.models.prediction import Prediction
from backend.models.project import Project
from backend.models.task import Task


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_project(db: Session, name: str = "Project") -> Project:
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def make_task(
    db: Session,
    title: str = "Task",
    *,
    project: Optional[Project] = None,
    importance: Importance = Importance.MEDIUM,
    deadline_in_days: Optional[float] = None,
    estimated_hours: Optional[float] = None,
    status: TaskStatus = TaskStatus.PENDING,
    **extra,
) -> Task:
    task = Task(
        title=title,
        project_id=project.id if project else None,
        importance=importance,
        deadline=utcnow() + timedelta(days=deadline_in_days) if deadline_in_days is not None else None,
        estimated_hours=estimated_hours,
        status=status,
        **extra,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def make_completed_task(
    db: Session,
    title: str = "Done",
    *,
    project: Optional[Project] = None,
    importance: Importance = Importance.MEDIUM,
    estimated_hours: float = 2.0,
    actual_hours: float = 2.0,
    completed_days_ago: float = 1.0,
) -> Task:
    return make_task(
        db,
        title,
        project=project,
        importance=importance,
        estimated_hours=estimated_hours,
        status=TaskStatus.COMPLETED,
        actual_hours=actual_hours,
        completed_at=utcnow() - timedelta(days=completed_days_ago),
    )


def make_resolved_prediction(
    db: Session,
    task: Task,
    category: str,
    *,
    predicted: float = 2.0,
    actual: float = 2.6,
    resolved_days_ago: float = 1.0,
) -> Prediction:
    """A resolved Prediction with error_pct computed the way estimator.resolve_prediction does."""
    prediction = Prediction(
        task_id=task.id,
        category=category,
        predicted_hours=predicted,
        actual_hours=actual,
        error_pct=(actual - predicted) / predicted * 100.0,
        resolved_at=utcnow() - timedelta(days=resolved_days_ago),
    )
    db.add(prediction)
    db.commit()
    return prediction
