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

from backend.ai import episodic_memory
from backend.ai.ollama_client import OllamaError, call_model
from backend.ai.prompts import WEEKLY_REVIEW_SYSTEM, build_weekly_review_prompt
from backend.models.enums import EpisodicEventType, ProjectStatus, TaskStatus
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

    _record_weekly_review_episode(db, period_start=period_start, period_end=today, stats=stats, recommendation=recommendation)

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


def _record_weekly_review_episode(
    db: Session, *, period_start: date_type, period_end: date_type, stats: dict, recommendation: str
) -> None:
    """
    Episodic Memory (PRD §63): weekly_review() runs live on every GET, so
    this can't just insert on every call -- episodic_memory.record_event()
    dedupes on (event_type, occurred_on, title), keyed here on the
    period's end date, so re-viewing the analytics page during the same
    week updates the one row for that week instead of creating a new one.
    Skipped entirely for a week with no activity at all -- an empty week
    isn't an event worth remembering.
    """
    if stats["tasks_completed"] == 0 and stats["hours_worked"] == 0:
        return
    title = f"Weekly review: {period_start.isoformat()} to {period_end.isoformat()}"
    summary = (
        f"{stats['tasks_completed']}/{stats['tasks_planned']} tasks completed, "
        f"{stats['hours_worked']}h worked. {recommendation}"
    )
    episodic_memory.record_event(
        db,
        EpisodicEventType.WEEKLY_REVIEW,
        title=title,
        summary=summary,
        occurred_on=period_end,
        payload={"period_start": period_start.isoformat(), **{k: v for k, v in stats.items() if k != "project_progress"}},
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


def personal_calibration(db: Session) -> list[dict]:
    """
    The "Personal Calibration" view (review Priority 4/#17): the same
    signed per-category bias estimation_error() reports above, but
    filtered down to exactly what ml/calibration.py is actually applying
    to new estimates right now — same MIN_SAMPLES/LOOKBACK_DAYS gate, so
    this is never out of sync with what the estimator is really doing.
    """
    from backend.ml import calibration as calibration_module

    project_names = {p.id: p.name for p in db.query(Project).all()}
    categories = {
        row[0]
        for row in db.query(Prediction.category).filter(Prediction.category.isnot(None)).distinct().all()
    }

    results = []
    for category in categories:
        cal = calibration_module.get_calibration(db, category)
        if cal is None:
            continue
        results.append(
            {
                "category": _category_display_name(category, project_names),
                "bias_pct": cal.bias_pct,
                "sample_count": cal.sample_count,
                "confidence": cal.confidence,
            }
        )
    results.sort(key=lambda c: abs(c["bias_pct"]), reverse=True)
    return results


ESTIMATION_ERROR_TREND_DAYS = 14


def get_estimation_error_trend(
    db: Session, days: int = ESTIMATION_ERROR_TREND_DAYS, now: Optional[datetime] = None
) -> list[dict]:
    """
    Historical estimation error, one point per day — the natural
    follow-up to the Execution Score trend, and the piece flagged as
    "still open" after Weekly Review/estimation-error trends weren't
    historized the same way.

    Backed by ProductivityMetric.estimation_error_pct, the same
    nightly-job-snapshotted rollup pattern get_execution_score_trend()
    already uses, rather than recomputing every historical day's error
    live (a day's estimation error is a property of what completed that
    day, so a stored snapshot is the correct historical record, not a
    live recompute against today's Predictions table).

    Note on definition: this is unsigned average absolute error (how far
    off, in either direction — see scheduler/nightly.py's _today_metrics),
    not the signed under/over-estimate bias that estimation_error() above
    reports. The two intentionally answer different questions ("how far
    off, on average" vs. "which direction do you tend to be off"); this
    trend is the former, matching what's actually persisted per day.

    Today's point is filled in live (same unsigned-error formula, not
    persisted) if the nightly job hasn't run yet today, so the trend line
    doesn't have a visible gap at the most recent day.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()
    start = today - timedelta(days=days - 1)

    rows = {
        m.date: m
        for m in db.query(ProductivityMetric)
        .filter(ProductivityMetric.date >= start, ProductivityMetric.date <= today)
        .all()
    }

    points: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = rows.get(day)
        if row is not None and row.estimation_error_pct is not None:
            average_error_pct = row.estimation_error_pct
        elif day == today:
            live = _live_estimation_error_pct(db, today)
            if live is None:
                continue  # nothing completed today yet — no point to plot
            average_error_pct = live
        else:
            continue  # no snapshot for a past day -- skip rather than fabricate a number
        points.append({"date": day, "average_error_pct": average_error_pct})

    return points


def _live_estimation_error_pct(db: Session, today: date_type) -> Optional[float]:
    """Read-only mirror of scheduler/nightly.py's _today_metrics() error
    calculation, for today's live trend point -- deliberately doesn't
    write a ProductivityMetric row itself (that's the nightly job's job);
    a GET route shouldn't have that side effect."""
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    completed_today = (
        db.query(Task)
        .filter(Task.status == TaskStatus.COMPLETED, Task.completed_at >= day_start, Task.completed_at < day_end)
        .all()
    )
    errors = [
        abs((t.actual_hours - t.estimated_hours) / t.estimated_hours) * 100
        for t in completed_today
        if t.actual_hours and t.estimated_hours
    ]
    return round(sum(errors) / len(errors), 2) if errors else None


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