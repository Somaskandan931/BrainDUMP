"""Small factories shared by the test modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.auth.security import create_access_token, hash_password
from backend.app.db.database import SessionLocal, owner_id
from backend.app.models.enums import Importance, TaskStatus
from backend.app.models.prediction import Prediction
from backend.app.models.project import Project
from backend.app.models.task import Task
from backend.app.models.user import User

# bcrypt is deliberately slow; hash once per test run instead of once per user.
TEST_PASSWORD = "correct-horse-battery"
_TEST_PASSWORD_HASH: Optional[str] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_user(email: str = "user@example.com", name: str = "Test User") -> User:
    """Insert a user (email/password login, password TEST_PASSWORD) on its own
    unscoped session and return it detached -- safe to read .id/.email from."""
    global _TEST_PASSWORD_HASH
    if _TEST_PASSWORD_HASH is None:
        _TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)

    session = SessionLocal()
    try:
        user = User(email=email, name=name, hashed_password=_TEST_PASSWORD_HASH)
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def scoped_session(user: User) -> Session:
    """A Session with tenant filtering turned on for `user` -- the same thing
    api.deps.get_scoped_db / the background jobs set up. Caller closes it."""
    session = SessionLocal()
    session.info["user_id"] = user.id
    return session


def make_project(db: Session, name: str = "Project") -> Project:
    project = Project(user_id=owner_id(db), name=name)
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
        user_id=owner_id(db),
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
        user_id=owner_id(db),
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
