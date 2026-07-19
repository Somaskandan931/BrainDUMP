"""
services/analytics_service.py — Milestone 8 aggregation pipeline.

Turns the four `/api/analytics/*` routes from `501` into real endpoints.
Every number here is computed with plain Python/SQL over existing tables
(ProductivityMetric, Task, Prediction, WorkSession, Project) — the only
place an LLM touches this module is the one-sentence recommendation in
weekly_review(), which explains numbers that were already computed, not
compute them itself (see backend/ai/prompts.py's WEEKLY_REVIEW_SYSTEM).

Design note on "why now, not cached": all four functions run live against
SQLite on each request rather than reading a pre-baked report. For a
single-user local install with a database that fits entirely in memory,
that's simpler and always-fresh; there's no multi-tenant load concern
that would justify a caching layer.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date as date_type, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.ai.ollama_client import OllamaError, call_model
from backend.ai.prompts import WEEKLY_REVIEW_SYSTEM, build_weekly_review_prompt
from backend.models.enums import ProjectStatus, TaskStatus
from backend.models.metrics import ProductivityMetric
from backend.models.prediction import Prediction
from backend.models.project import Project
from backend.models.session import WorkSession
from backend.models.task import Task
from backend.schemas.analytics import (
    CategoryEstimationError,
    EstimationErrorResponse,
    HourBucket,
    ProductivityHoursResponse,
    ProjectProgress,
    StreaksResponse,
    WeeklyReviewResponse,
)

logger = logging.getLogger(__name__)

WEEKLY_REVIEW_WINDOW_DAYS = 7
PRODUCTIVITY_HOURS_LOOKBACK_DAYS = 30
STREAK_LOOKUP_DAYS = 180  # far enough back that "longest streak ever" doesn't quietly cap itself

# A category's average error is only called out as a real bias once it
# clears this threshold — a handful of percentage points either way is
# noise, not a pattern worth acting on.
_BIAS_NOISE_THRESHOLD_PCT = 5.0
# Only worth naming in the weekly-review recommendation once the average
# underestimate crosses this bar.
_UNDERESTIMATE_CALLOUT_THRESHOLD_PCT = 15.0


# ---------------------------------------------------------------------------
# Weekly review
# ---------------------------------------------------------------------------


def weekly_review(db: Session) -> WeeklyReviewResponse:
    today = datetime.now(timezone.utc).date()
    period_start = today - timedelta(days=WEEKLY_REVIEW_WINDOW_DAYS - 1)

    metrics = (
        db.query(ProductivityMetric)
        .filter(ProductivityMetric.date >= period_start, ProductivityMetric.date <= today)
        .order_by(ProductivityMetric.date)
        .all()
    )

    tasks_completed = sum(m.tasks_completed for m in metrics)
    tasks_planned = sum(m.tasks_planned for m in metrics)
    hours_worked = round(sum(m.hours_worked for m in metrics), 2)
    completion_rate = round(tasks_completed / tasks_planned, 3) if tasks_planned > 0 else None

    most_productive_day: Optional[str] = None
    least_productive_day: Optional[str] = None
    active_days = [m for m in metrics if m.hours_worked > 0]
    if active_days:
        by_hours = sorted(active_days, key=lambda m: m.hours_worked, reverse=True)
        most_productive_day = by_hours[0].date.strftime("%A")
        least_productive_day = by_hours[-1].date.strftime("%A")

    error_report = estimation_error(db, since=period_start)
    most_underestimated_category: Optional[str] = None
    most_underestimated_pct: Optional[float] = None
    underestimated = [c for c in error_report.by_category if c.bias == "underestimates"]
    if underestimated:
        worst = max(underestimated, key=lambda c: c.average_error_pct)
        most_underestimated_category = worst.category
        most_underestimated_pct = worst.average_error_pct

    now = datetime.now(timezone.utc)
    missed_deadlines = (
        db.query(Task)
        .filter(
            Task.deadline.isnot(None),
            Task.deadline < now,
            Task.status.notin_((TaskStatus.COMPLETED, TaskStatus.CANCELLED)),
        )
        .count()
    )

    project_progress = _project_progress(db)

    stats = {
        "period_start": period_start.isoformat(),
        "period_end": today.isoformat(),
        "tasks_completed": tasks_completed,
        "tasks_planned": tasks_planned,
        "completion_rate": completion_rate,
        "hours_worked": hours_worked,
        "most_productive_day": most_productive_day,
        "least_productive_day": least_productive_day,
        "most_underestimated_category": most_underestimated_category,
        "most_underestimated_pct": most_underestimated_pct,
        "missed_deadlines": missed_deadlines,
        "project_progress": [p.model_dump() for p in project_progress],
    }
    recommendation, ai_generated = _weekly_recommendation(stats)

    return WeeklyReviewResponse(
        period_start=period_start,
        period_end=today,
        tasks_completed=tasks_completed,
        tasks_planned=tasks_planned,
        completion_rate=completion_rate,
        hours_worked=hours_worked,
        most_productive_day=most_productive_day,
        least_productive_day=least_productive_day,
        most_underestimated_category=most_underestimated_category,
        most_underestimated_pct=most_underestimated_pct,
        missed_deadlines=missed_deadlines,
        project_progress=project_progress,
        recommendation=recommendation,
        ai_generated=ai_generated,
    )


def _project_progress(db: Session) -> list[ProjectProgress]:
    projects = db.query(Project).filter(Project.status == ProjectStatus.ACTIVE).all()
    progress = []
    for project in projects:
        total = len(project.tasks)
        if total == 0:
            continue
        completed = sum(1 for t in project.tasks if t.status == TaskStatus.COMPLETED)
        progress.append(
            ProjectProgress(
                project_id=project.id,
                project_name=project.name,
                tasks_total=total,
                tasks_completed=completed,
                completion_rate=round(completed / total, 3),
            )
        )
    return progress


def _weekly_recommendation(stats: dict) -> tuple[str, bool]:
    """
    Returns (recommendation_text, ai_generated). Tries the local Reflection
    Agent first; falls back to a rule-based sentence if Ollama isn't
    running or returns something unusable -- the analytics page should
    never break, or go silent, just because the local model is offline.
    """
    try:
        raw = call_model(
            build_weekly_review_prompt(json.dumps(stats)),
            system=WEEKLY_REVIEW_SYSTEM,
            json_mode=False,
            temperature=0.4,
        )
        text = raw.strip().strip('"')
        if text:
            return text, True
    except OllamaError as exc:
        logger.info("analytics_service: weekly review AI recommendation skipped (%s)", exc)

    return _rule_based_recommendation(stats), False


def _rule_based_recommendation(stats: dict) -> str:
    if (
        stats["most_underestimated_category"]
        and stats["most_underestimated_pct"] is not None
        and stats["most_underestimated_pct"] > _UNDERESTIMATE_CALLOUT_THRESHOLD_PCT
    ):
        return (
            f"You underestimated {stats['most_underestimated_category']} by "
            f"{stats['most_underestimated_pct']:.0f}% this week — start those tasks a day or two earlier."
        )
    if stats["missed_deadlines"] > 0:
        return (
            f"You have {stats['missed_deadlines']} task(s) past their deadline — "
            "worth replanning or adjusting them rather than letting them sit."
        )
    if stats["completion_rate"] is not None and stats["completion_rate"] < 0.6:
        return "Completion rate dipped below 60% this week — try scheduling fewer tasks per day."
    if stats["tasks_completed"] == 0:
        return "No completed tasks logged this week — a Brain Dump is the fastest way to get a plan going again."
    return (
        f"Solid week: {stats['tasks_completed']} task(s) done across "
        f"{stats['hours_worked']:.1f} hours — keep the pace."
    )


# ---------------------------------------------------------------------------
# Estimation error
# ---------------------------------------------------------------------------


def estimation_error(db: Session, *, since: Optional[date_type] = None) -> EstimationErrorResponse:
    query = db.query(Prediction).filter(
        Prediction.actual_hours.isnot(None), Prediction.error_pct.isnot(None)
    )
    if since is not None:
        since_dt = datetime.combine(since, time.min, tzinfo=timezone.utc)
        query = query.filter(Prediction.resolved_at >= since_dt)
    predictions = query.all()

    overall_sample_count = len(predictions)
    overall_average_error_pct = (
        round(sum(p.error_pct for p in predictions) / overall_sample_count, 2)
        if overall_sample_count
        else None
    )

    project_names = {p.id: p.name for p in db.query(Project).all()}

    grouped: dict[str, list[float]] = defaultdict(list)
    for prediction in predictions:
        grouped[_category_display_name(prediction.category, project_names)].append(prediction.error_pct)

    by_category = []
    for category, errors in grouped.items():
        average = sum(errors) / len(errors)
        if average > _BIAS_NOISE_THRESHOLD_PCT:
            bias = "underestimates"  # actual took longer than predicted
        elif average < -_BIAS_NOISE_THRESHOLD_PCT:
            bias = "overestimates"
        else:
            bias = "accurate"
        by_category.append(
            CategoryEstimationError(
                category=category,
                sample_count=len(errors),
                average_error_pct=round(average, 2),
                bias=bias,
            )
        )
    by_category.sort(key=lambda c: abs(c.average_error_pct), reverse=True)

    return EstimationErrorResponse(
        overall_average_error_pct=overall_average_error_pct,
        overall_sample_count=overall_sample_count,
        by_category=by_category,
    )


def _category_display_name(category: Optional[str], project_names: dict[int, str]) -> str:
    """
    Prediction.category is either a stringified project_id (task belonged
    to a project) or an Importance value like "high" (one-off task) — see
    ml/estimator.py::ensure_estimate(). Resolve the former to a readable
    project name; leave the latter as-is.
    """
    if category is None:
        return "uncategorized"
    if category.isdigit() and int(category) in project_names:
        return project_names[int(category)]
    return category


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------


def streaks(db: Session) -> StreaksResponse:
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=STREAK_LOOKUP_DAYS)

    rows = (
        db.query(ProductivityMetric.date)
        .filter(ProductivityMetric.tasks_completed > 0, ProductivityMetric.date >= since)
        .all()
    )
    active_dates = sorted({row[0] for row in rows})

    if not active_dates:
        return StreaksResponse(
            current_streak_days=0, longest_streak_days=0, active_today=False, last_active_date=None
        )

    active_set = set(active_dates)

    longest = 1
    run = 1
    for i in range(1, len(active_dates)):
        if (active_dates[i] - active_dates[i - 1]).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)

    active_today = today in active_set
    # One day's grace: a streak that was alive through yesterday still
    # counts as "current" today (the day isn't over yet), matching how
    # most habit-streak UX behaves rather than zeroing out at midnight.
    cursor = today if active_today else today - timedelta(days=1)
    current = 0
    while cursor in active_set:
        current += 1
        cursor -= timedelta(days=1)

    return StreaksResponse(
        current_streak_days=current,
        longest_streak_days=longest,
        active_today=active_today,
        last_active_date=active_dates[-1],
    )


# ---------------------------------------------------------------------------
# Productivity by hour
# ---------------------------------------------------------------------------


def productivity_hours(
    db: Session, *, lookback_days: int = PRODUCTIVITY_HOURS_LOOKBACK_DAYS
) -> ProductivityHoursResponse:
    """
    Buckets logged WorkSession minutes by hour-of-day. Note: start_time is
    stored as a timezone-aware UTC datetime, and .hour below reads it in
    UTC -- same naive-time caveat config.py already documents for the
    scheduler's working-hour window (WORK_DAY_START_HOUR/END_HOUR are
    naive local time). A real per-user timezone setting is future scope;
    for a single local install where server and user share a timezone,
    this only actually diverges from "local hour" for users who aren't in
    UTC, which is a known simplification, not a silent bug.
    """
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    sessions = (
        db.query(WorkSession)
        .filter(WorkSession.start_time >= since, WorkSession.duration_minutes.isnot(None))
        .all()
    )

    minutes_by_hour: dict[int, list[int]] = defaultdict(list)
    for session in sessions:
        minutes_by_hour[session.start_time.hour].append(session.duration_minutes)

    by_hour = [
        HourBucket(
            hour=hour,
            hours_logged=round(sum(minutes_by_hour.get(hour, [])) / 60, 2),
            sessions_count=len(minutes_by_hour.get(hour, [])),
        )
        for hour in range(24)
    ]

    active_hours = [b for b in by_hour if b.sessions_count > 0]
    best_hour = max(active_hours, key=lambda b: b.hours_logged).hour if active_hours else None

    return ProductivityHoursResponse(by_hour=by_hour, best_hour=best_hour, lookback_days=lookback_days)
