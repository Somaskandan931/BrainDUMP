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
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from backend.database import SessionLocal
from backend.integrations.google_calendar import GoogleCalendarError
from backend.models.calendar_event import CalendarEvent
from backend.models.metrics import ProductivityMetric
from backend.models.enums import EventSource, TaskStatus
from backend.models.task import Task
from backend.models.settings import Setting
from backend.services import calendar_sync_service, deadline_service

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "last_nightly_summary"


def _today_metrics(db, today: date) -> ProductivityMetric:
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
        metric = ProductivityMetric(date=today)
        db.add(metric)

    metric.hours_worked = round(hours_worked, 2)
    metric.tasks_completed = len(completed_today)
    metric.tasks_planned = tasks_planned
    metric.completion_rate = round(len(completed_today) / tasks_planned, 3) if tasks_planned > 0 else None
    metric.estimation_error_pct = estimation_error_pct
    return metric


def run_nightly_job() -> dict:
    """Entry point registered with APScheduler in app.py. Owns its own DB session."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today = now.date()

        metric = _today_metrics(db, today)
        replan_result = deadline_service.replan(db)

        try:
            calendar_push = calendar_sync_service.push_pending_sessions(db)
            calendar_sync_result = {"pushed": calendar_push[0], "errors": calendar_push[1]}
        except GoogleCalendarError as exc:
            logger.info("Nightly job: Google Calendar push skipped (%s)", exc)
            calendar_sync_result = {"pushed": 0, "errors": [str(exc)]}

        # Weekly (Sunday) retrain of ml/estimator.py's regressor. Wrapped
        # broadly -- sklearn/joblib issues (missing optional dep, a
        # corrupt models/ dir, low disk space) shouldn't take down the
        # rest of the nightly job, which is the part with actual
        # user-facing consequences (replan, calendar sync).
        ml_retrain_result: dict = {"ran": False}
        if today.weekday() == 6:  # Sunday
            try:
                from backend.ml import trainer as ml_trainer

                ml_retrain_result = {"ran": True, **ml_trainer.train_estimator(db).to_dict()}
            except Exception as exc:  # noqa: BLE001 - see comment above
                logger.warning("Nightly job: estimator retrain failed (%s)", exc)
                ml_retrain_result = {"ran": True, "trained": False, "reason": str(exc)}

        summary = {
            "generated_at": now.isoformat(),
            "tasks_completed_today": metric.tasks_completed,
            "tasks_planned_today": metric.tasks_planned,
            "hours_worked_today": metric.hours_worked,
            "rescheduled_count": replan_result["rescheduled_count"],
            "demoted_count": len(replan_result["demoted_tasks"]),
            "at_risk_count": len(replan_result["at_risk_tasks"]),
            "calendar_sync": calendar_sync_result,
            "ml_retrain": ml_retrain_result,
        }

        setting = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
        if setting is None:
            setting = Setting(key=_SETTINGS_KEY, value=json.dumps(summary))
            db.add(setting)
        else:
            setting.value = json.dumps(summary)
        db.commit()

        logger.info(
            "Nightly job: %d completed today, %d rescheduled, %d at risk",
            summary["tasks_completed_today"],
            summary["rescheduled_count"],
            summary["at_risk_count"],
        )
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    # `python -m backend.scheduler.nightly` — manual run for testing.
    print(json.dumps(run_nightly_job(), indent=2))
