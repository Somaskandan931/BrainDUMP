"""
scheduler/nightly.py — Nightly job (runs ~11 PM via APScheduler, see app.py).

Milestone 5 implementation:
1. Tally today's completed tasks/hours (from Task.completed_at + WorkSession).
2. Call deadline_service.replan() — detects at-risk tasks, demotes
   low/medium importance ones that are at risk, wipes and repacks the
   future schedule so unfinished work actually fits the remaining time.
3. Write a ProductivityMetric row for today (the daily rollup Weekly
   Review/Analytics reads from, instead of recomputing from raw sessions
   every time).
4. On Sundays: retrain ml/estimator.py's regressor
   (backend.ml.trainer.train_estimator()) against the week's freshly
   resolved Predictions. Weekly Review itself is NOT generated or cached
   here — GET /api/analytics/weekly-review computes it live and cheaply
   on request, so there's nothing worth pre-baking; this job only does
   the one thing that's actually expensive to redo per-request (fitting
   a model).

Milestone 6 adds: after replanning, push the freshly-repacked schedule
to Google Calendar. Wrapped in try/except so an unconfigured integration
degrades this one step, not the whole job.

Milestone 8 adds: tasks_planned on today's ProductivityMetric is now a
real count (distinct tasks with a Brain-Dump-scheduled CalendarEvent
today), not a placeholder — see _today_metrics(). completion_rate can
finally be computed from it.

Multi-user auth follow-up: same fix as scheduler/morning.py -- this
used to run once, globally. run_nightly_job() now loops over every
active User and runs the whole pipeline (replan, calendar push,
long-term memory refresh, notifications) once per user, with
db.info["user_id"] set by hand for that iteration. The Sunday ML
retrain is a schema-level exception: ml/trainer.py trains one global
regressor from whichever user's session happens to be active when it's
called, which only makes sense once per night, not once per user --
see the note at its call site below.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from backend.app.db.database import SessionLocal, owner_id
from backend.app.ai import long_term_memory
from backend.app.integrations.google_calendar import GoogleCalendarError
from backend.app.models.calendar_event import CalendarEvent
from backend.app.models.metrics import ProductivityMetric
from backend.app.models.enums import EventSource, TaskStatus
from backend.app.models.task import Task
from backend.app.models.settings import Setting
from backend.app.models.user import User
from backend.app.services.integrations import calendar_sync_service
from backend.app.services.planning import deadline_service
from backend.app.services.productivity import execution_score_service, notification_service

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "last_nightly_summary"


def _today_metrics(db, today: date, now: datetime) -> ProductivityMetric:
    day_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    completed_today = (
        db.query(Task)
        .filter(Task.status == TaskStatus.COMPLETED, Task.completed_at >= day_start, Task.completed_at < day_end)
        .all()
    )
    hours_worked = sum(t.actual_hours or 0.0 for t in completed_today)

    errors = [
        abs((t.actual_hours - t.estimated_hours) / t.estimated_hours) * 100
        for t in completed_today
        if t.actual_hours and t.estimated_hours
    ]
    estimation_error_pct = round(sum(errors) / len(errors), 2) if errors else None

    # "Planned" = distinct tasks the morning job (or a same-day replan)
    # actually scheduled a work-session block for today. Only Brain-Dump-
    # created blocks count -- imported Google events (source=GOOGLE, e.g.
    # "College") aren't Brain Dump's plan for the user's work, so they'd
    # inflate the denominator without meaning anything for completion_rate.
    planned_task_ids = {
        row[0]
        for row in db.query(CalendarEvent.task_id)
        .filter(
            CalendarEvent.source == EventSource.BRAIN_DUMP,
            CalendarEvent.task_id.isnot(None),
            CalendarEvent.start_time >= day_start,
            CalendarEvent.start_time < day_end,
        )
        .distinct()
        .all()
    }
    tasks_planned = len(planned_task_ids)

    metric = db.query(ProductivityMetric).filter(ProductivityMetric.date == today).first()
    if metric is None:
        metric = ProductivityMetric(user_id=owner_id(db), date=today)
        db.add(metric)

    metric.hours_worked = round(hours_worked, 2)
    metric.tasks_completed = len(completed_today)
    metric.tasks_planned = tasks_planned
    metric.completion_rate = round(len(completed_today) / tasks_planned, 3) if tasks_planned > 0 else None
    metric.estimation_error_pct = estimation_error_pct

    # Snapshot today's Execution Score (PRD §15/§37) so the trend view has
    # a real history point for today, computed with the same `now` used
    # for the rest of tonight's run rather than a fresh timestamp.
    try:
        metric.execution_score = execution_score_service.compute_execution_score(db, now=now).score
    except Exception as exc:  # noqa: BLE001 - a scoring bug shouldn't block the rest of the nightly job
        logger.warning("Nightly job: execution score snapshot failed (%s)", exc)

    return metric


def _run_nightly_job_for_user(db, today: date, now: datetime) -> dict:
    """The full per-user pipeline (everything except the Sunday ML
    retrain, which trains one shared model across every user's history
    -- see run_nightly_job()), run against a session already scoped
    (db.info["user_id"] set) to exactly one user."""
    metric = _today_metrics(db, today, now)
    replan_result = deadline_service.replan(db)

    try:
        calendar_push = calendar_sync_service.push_pending_sessions(db)
        calendar_sync_result = {"pushed": calendar_push[0], "errors": calendar_push[1]}
    except GoogleCalendarError as exc:
        logger.info("Nightly job: Google Calendar push skipped (%s)", exc)
        calendar_sync_result = {"pushed": 0, "errors": [str(exc)]}

    # Long-Term Memory (PRD §63) refresh -- recomputes preferred hours,
    # estimation bias, and recent project history from tonight's fully
    # up-to-date data. Wrapped: a bug here shouldn't take down
    # replan/calendar sync, which matter more.
    try:
        long_term_memory.refresh_profile(db)
    except Exception as exc:  # noqa: BLE001 - see comment above
        logger.warning("Nightly job: long-term memory refresh failed (%s)", exc)

    summary = {
        "generated_at": now.isoformat(),
        "tasks_completed_today": metric.tasks_completed,
        "tasks_planned_today": metric.tasks_planned,
        "hours_worked_today": metric.hours_worked,
        "rescheduled_count": replan_result["rescheduled_count"],
        "demoted_count": len(replan_result["demoted_tasks"]),
        "at_risk_count": len(replan_result["at_risk_tasks"]),
        "calendar_sync": calendar_sync_result,
        "notifications": notification_service.generate_notifications(db, now),
    }

    setting = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
    if setting is None:
        setting = Setting(user_id=owner_id(db), key=_SETTINGS_KEY, value=json.dumps(summary))
        db.add(setting)
    else:
        setting.value = json.dumps(summary)
    db.commit()

    logger.info(
        "Nightly job (user %s): %d completed today, %d rescheduled, %d at risk",
        db.info.get("user_id"),
        summary["tasks_completed_today"],
        summary["rescheduled_count"],
        summary["at_risk_count"],
    )
    return summary


def run_nightly_job() -> dict:
    """
    Entry point registered with APScheduler in app.py. Owns its own DB
    session, loops over every active user running the per-user pipeline
    with tenant filtering turned on for that iteration, then -- once,
    outside the loop, on Sundays -- retrains ml/estimator.py's
    regressor across every user's resolved Predictions combined.

    That retrain is deliberately the one piece of this job that stays
    unscoped (no db.info["user_id"] set for it): ml/trainer.py persists
    a single MODELS_DIR/estimator.pkl that ml/estimator.py's whole
    process loads regardless of which user is being served, so training
    it per-user would just mean whichever user happened to run last in
    the loop silently overwrote the shared model with only their own
    (usually much smaller) history. Training the one shared duration-
    prediction model on the pooled feature set (importance/energy/
    has_project/has_deadline -- no task titles or other identifying
    content, see ml/trainer.py's feature engineering) isn't a privacy
    regression the way pooling raw task data across users' *reads*
    would be; it only ever comes back out as a number, never as
    another user's task content.

    Returns {"users": {user_id: summary}, "ml_retrain": {...}}. A
    user's per-user run failing is logged and recorded as
    {"error": str(exc)} rather than aborting everyone else's night.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today = now.date()

        user_ids = [row[0] for row in db.query(User.id).filter(User.is_active.is_(True)).all()]

        user_results: dict = {}
        for user_id in user_ids:
            db.info["user_id"] = user_id
            try:
                user_results[user_id] = _run_nightly_job_for_user(db, today, now)
            except Exception as exc:  # noqa: BLE001 - one user's bug shouldn't skip everyone else's nightly job
                db.rollback()
                logger.exception("Nightly job failed for user %d", user_id)
                user_results[user_id] = {"error": str(exc)}
            finally:
                db.info.pop("user_id", None)

        # Weekly (Sunday) retrain -- see docstring above for why this runs
        # once, unscoped, after every user's own pipeline has finished.
        # Wrapped broadly: sklearn/joblib issues (missing optional dep, a
        # corrupt models/ dir, low disk space) shouldn't take down a run
        # that already succeeded for every user above.
        ml_retrain_result: dict = {"ran": False}
        if today.weekday() == 6:  # Sunday
            try:
                from backend.app.ml import trainer as ml_trainer

                ml_retrain_result = {"ran": True, **ml_trainer.train_estimator(db).to_dict()}
            except Exception as exc:  # noqa: BLE001 - see comment above
                logger.warning("Nightly job: estimator retrain failed (%s)", exc)
                ml_retrain_result = {"ran": True, "trained": False, "reason": str(exc)}

        return {"users": user_results, "ml_retrain": ml_retrain_result}
    finally:
        db.close()


if __name__ == "__main__":
    # `python -m backend.scheduler.nightly` — manual run for testing.
    print(json.dumps(run_nightly_job(), indent=2))
