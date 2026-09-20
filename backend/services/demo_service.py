"""
services/demo_service.py — "Load Demo Workspace" (review Priority 5).

A brand-new install has no history, which means the parts of BrainDUMP
that are actually interesting — personal calibration, the Execution
Score, streaks, Plan-vs-Reality — have nothing to show yet. This module
seeds realistic *synthetic* history (clearly labeled as such, never
mixed silently into real data) so the whole intelligence layer lights
up immediately for a demo or a first look at the product, per the
review's explicit "don't fake live production data, but a clearly
labeled demo workspace is legitimate and professional."

Every demo project's name is prefixed "[Demo]" and its description
states it's synthetic, so it's never mistaken for real work in any
existing view (project list, dashboard, analytics) without touching
those views' code at all. reset_demo_workspace() removes every "[Demo]"
project (and, via cascade, every task/session/prediction that hangs off
it) without disturbing anything else.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from backend.database import owner_id
from backend.models.dependency import Dependency
from backend.models.enums import Importance, TaskStatus
from backend.models.metrics import ProductivityMetric
from backend.models.prediction import Prediction
from backend.models.project import Project
from backend.models.session import WorkSession
from backend.models.settings import Setting
from backend.models.task import Task

DEMO_PREFIX = "[Demo]"
DEMO_DESCRIPTION = "Demo workspace — synthetic history, generated to preview BrainDUMP's calibration and analytics."

# One entry per demo project: (name, category description, signed bias
# applied to completed tasks' actual_hours vs. their estimate — mirrors
# the review's own worked examples, e.g. "Research tasks: +34%",
# "Admin: -8%").
_DEMO_PROJECTS = [
    ("IEEE Paper", Importance.HIGH, 0.34),
    ("ML Interview Prep", Importance.HIGH, 0.24),
    ("Admin & Ops", Importance.LOW, -0.08),
]

_TASK_TITLES = {
    "IEEE Paper": ["Review methodology", "Run experiments", "Update results", "Rewrite discussion", "Final proofreading"],
    "ML Interview Prep": ["SQL revision", "ML fundamentals review", "Mock interview", "System design practice"],
    "Admin & Ops": ["Weekly report", "Inbox cleanup", "Update project tracker", "Renew subscriptions"],
}

# ProductivityMetric has no "is demo" marker (and adding a column just for
# this would be a schema change), so the dates the seed created are recorded
# here and reset_demo_workspace() deletes exactly those rows -- without
# this, reset removed the [Demo] projects but left ~3 weeks of synthetic
# streak/productivity history behind in the real analytics.
_DEMO_METRIC_DATES_KEY = "demo_metric_dates"

_HISTORY_DAYS = 21
_RNG_SEED = 42


@dataclass
class DemoSeedResult:
    projects_created: int
    tasks_completed: int
    tasks_pending: int
    sessions_created: int
    predictions_created: int
    metrics_days: int
    # True when a demo workspace already existed, so nothing new was created.
    already_seeded: bool = False


def _make_completed_task(
    db: Session,
    project: Project,
    title: str,
    importance: Importance,
    bias: float,
    completed_at: datetime,
    rng: random.Random,
) -> Task:
    base_estimate = round(rng.uniform(1.5, 4.0), 2)
    # Realistic noise on top of the category's systematic bias, so not
    # every task in a project shows the exact same error percentage.
    actual = round(max(0.25, base_estimate * (1 + bias + rng.uniform(-0.08, 0.08))), 2)

    task = Task(
        user_id=owner_id(db),
        project_id=project.id,
        title=title,
        status=TaskStatus.COMPLETED,
        importance=importance,
        estimated_hours=base_estimate,
        actual_hours=actual,
        confidence_score=0.7,
        completed_at=completed_at,
    )
    db.add(task)
    db.flush()

    error_pct = round((actual - base_estimate) / base_estimate * 100, 2)
    db.add(
        Prediction(
            user_id=owner_id(db),
            task_id=task.id,
            category=str(project.id),
            predicted_hours=base_estimate,
            actual_hours=actual,
            error_pct=error_pct,
            resolved_at=completed_at,
        )
    )
    db.add(
        WorkSession(
            user_id=owner_id(db),
            task_id=task.id,
            start_time=completed_at - timedelta(hours=actual),
            end_time=completed_at,
            duration_minutes=int(actual * 60),
            predicted_duration_minutes=int(base_estimate * 60),
        )
    )
    return task


def seed_demo_workspace(db: Session) -> dict:
    """
    Idempotent-ish: calling this twice creates a second, distinctly-named
    batch (dated in the title) rather than erroring — but the normal flow
    is reset_demo_workspace() first if the caller wants a clean slate.
    """
    # A second click (or a double-submit from the UI button) must not stack
    # a duplicate batch on top of the first -- reset first to regenerate.
    if db.query(Project.id).filter(Project.name.startswith(DEMO_PREFIX)).first() is not None:
        return DemoSeedResult(0, 0, 0, 0, 0, 0, already_seeded=True).__dict__

    rng = random.Random(_RNG_SEED)
    now = datetime.now(timezone.utc)

    projects_created = 0
    tasks_completed = 0
    tasks_pending = 0
    sessions_created = 0
    predictions_created = 0

    for name, importance, bias in _DEMO_PROJECTS:
        project = Project(
            user_id=owner_id(db),
            name=f"{DEMO_PREFIX} {name}",
            description=DEMO_DESCRIPTION,
        )
        db.add(project)
        db.flush()
        projects_created += 1

        titles = _TASK_TITLES[name]
        completed_titles, pending_titles = titles[:-1], titles[-1:]

        previous_task: Task | None = None
        for i, title in enumerate(completed_titles):
            days_ago = _HISTORY_DAYS - (i * (_HISTORY_DAYS // max(1, len(completed_titles))))
            completed_at = now - timedelta(days=max(1, days_ago), hours=rng.uniform(0, 6))
            task = _make_completed_task(db, project, title, importance, bias, completed_at, rng)
            tasks_completed += 1
            sessions_created += 1
            predictions_created += 1
            previous_task = task

        # One still-open task per project, with a near deadline and (for
        # the first project) a dependency on the last completed task, so
        # the demo also shows an active, at-risk-capable schedule and a
        # real dependency edge — not just historical data.
        for title in pending_titles:
            pending = Task(
                user_id=owner_id(db),
                project_id=project.id,
                title=title,
                status=TaskStatus.PENDING,
                importance=importance,
                deadline=now + timedelta(days=rng.uniform(2, 6)),
            )
            db.add(pending)
            db.flush()
            tasks_pending += 1
            if previous_task is not None:
                db.add(Dependency(user_id=owner_id(db), task_id=pending.id, depends_on_task_id=previous_task.id))

    db.commit()

    # Daily rollups so streaks/productivity-hours/weekly-review have
    # something to read without waiting for the nightly job to run.
    # Starts at yesterday: today's row belongs to the real nightly job, so a
    # demo row there could be overwritten by (or later delete) real data.
    metrics_days = 0
    seeded_dates: List[str] = []
    for offset in range(1, _HISTORY_DAYS + 1):
        day = (now - timedelta(days=offset)).date()
        if db.query(ProductivityMetric).filter(ProductivityMetric.date == day).first():
            continue
        seeded_dates.append(day.isoformat())
        worked = round(rng.uniform(1.0, 5.0), 2) if rng.random() > 0.15 else 0.0
        db.add(
            ProductivityMetric(
                user_id=owner_id(db),
                date=day,
                hours_worked=worked,
                tasks_completed=rng.randint(0, 3) if worked else 0,
                tasks_planned=rng.randint(1, 4),
                completion_rate=round(rng.uniform(0.5, 1.0), 2) if worked else 0.0,
                estimation_error_pct=round(rng.uniform(5, 30), 2) if worked else None,
                execution_score=rng.randint(55, 90) if worked else None,
            )
        )
        metrics_days += 1
    if seeded_dates:
        db.add(Setting(user_id=owner_id(db), key=_DEMO_METRIC_DATES_KEY, value=json.dumps(seeded_dates)))
    db.commit()

    return DemoSeedResult(
        projects_created=projects_created,
        tasks_completed=tasks_completed,
        tasks_pending=tasks_pending,
        sessions_created=sessions_created,
        predictions_created=predictions_created,
        metrics_days=metrics_days,
    ).__dict__


def reset_demo_workspace(db: Session) -> dict:
    """Delete every [Demo]-prefixed project — cascades to its tasks,
    subtasks, sessions, predictions, and dependencies — leaving any real
    data untouched."""
    demo_projects: List[Project] = db.query(Project).filter(Project.name.startswith(DEMO_PREFIX)).all()
    count = len(demo_projects)
    for project in demo_projects:
        db.delete(project)

    setting = db.query(Setting).filter(Setting.key == _DEMO_METRIC_DATES_KEY).first()
    metrics_removed = 0
    if setting is not None:
        dates = [datetime.fromisoformat(d).date() for d in json.loads(setting.value or "[]")]
        if dates:
            metrics_removed = (
                db.query(ProductivityMetric)
                .filter(ProductivityMetric.date.in_(dates))
                .delete(synchronize_session=False)
            )
        db.delete(setting)

    db.commit()
    return {"projects_removed": count, "metrics_removed": metrics_removed}