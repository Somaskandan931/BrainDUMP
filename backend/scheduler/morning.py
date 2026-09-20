"""
scheduler/morning.py — Morning job (runs ~7 AM via APScheduler, see app.py).

Milestone 5 implementation:
1. schedule_pending_tasks() packs any not-yet-scheduled active tasks into
   free slots, reading busy time from the CalendarEvent table.
2. get_next_task() computes today's single "Do Next" recommendation.

Milestone 6 adds real Google Calendar sync around that core:
0. Pull real Google Calendar events first, so step 1 above carves around
   actual meetings/classes, not just previously-scheduled Brain Dump
   sessions.
3. Push today's newly scheduled sessions to Google Calendar. Wrapped in
   try/except: an unconfigured integration (no credentials.json yet)
   degrades the morning job to "just don't sync that one thing" rather
   than failing the whole run.

Daily Planner narration (previously a documented gap in ai/prompts.py):
4. _daily_narration() turns the plan already computed by steps 1-3 above
   into one short prose sentence via the local model, same
   call_model()/OllamaError-fallback pattern analytics_service.py's
   weekly review recommendation already uses -- generated once per
   morning run and cached in the summary below, not recomputed on every
   page load (unlike weekly_review(), which runs live per request; a
   day's plan doesn't change fast enough to justify a live Ollama call
   on every dashboard fetch, and today's local-model latency is real).

Everything is written to the settings table under "last_morning_summary"
as the dashboard payload. GET /api/planner/today (api/planner.py) reads
it back for the frontend; it's a read of the last morning job's output,
not a live recomputation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.ai.ollama_client import OllamaError, call_model
from backend.ai.prompts import DAILY_PLANNER_SYSTEM, build_daily_planner_prompt
from backend.database import SessionLocal
from backend.integrations.google_calendar import GoogleCalendarError
from backend.models.settings import Setting
from backend.services import calendar_sync_service, notification_service, scheduler_service

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "last_morning_summary"


def _try_sync_calendar(db) -> dict:
    try:
        return calendar_sync_service.sync_calendar(db)
    except GoogleCalendarError as exc:
        logger.info("Morning job: Google Calendar sync skipped (%s)", exc)
        return {"pulled": 0, "pushed": 0, "removed": 0, "errors": [str(exc)]}


def _daily_narration(plan: dict) -> tuple[str, bool]:
    """
    Returns (narration_text, ai_generated). Tries the local Daily Planner
    narrator first; falls back to a rule-based sentence if Ollama isn't
    running or returns something unusable -- same reasoning as
    analytics_service._weekly_recommendation: the morning job (and the
    dashboard reading its output) should never break, or go silent, just
    because the local model is offline.
    """
    try:
        raw = call_model(
            build_daily_planner_prompt(json.dumps(plan)),
            system=DAILY_PLANNER_SYSTEM,
            json_mode=False,
            temperature=0.4,
        )
        text = raw.strip().strip('"')
        if text:
            return text, True
    except OllamaError as exc:
        logger.info("Morning job: daily narration skipped (%s)", exc)

    return _rule_based_narration(plan), False


def _rule_based_narration(plan: dict) -> str:
    next_title = plan.get("next_task_title")
    scheduled_count = plan.get("scheduled_count", 0)
    at_risk_count = plan.get("at_risk_count", 0)

    if not next_title and scheduled_count == 0:
        return "Nothing scheduled yet today — try a brain dump or add a task to get started."

    if next_title:
        sessions = "session" if scheduled_count == 1 else "sessions"
        sentence = f'Start with "{next_title}" — {scheduled_count} focus {sessions} scheduled today.'
    else:
        sessions = "session" if scheduled_count == 1 else "sessions"
        sentence = f"{scheduled_count} focus {sessions} scheduled today."

    if at_risk_count > 0:
        task_word = "task needs" if at_risk_count == 1 else "tasks need"
        sentence += f" {at_risk_count} {task_word} attention."

    return sentence


def run_morning_job() -> dict:
    """Entry point registered with APScheduler in app.py. Owns its own DB session."""
    db = SessionLocal()
    try:
        calendar_result = _try_sync_calendar(db)

        scheduled = scheduler_service.schedule_pending_tasks(db)
        next_task = scheduler_service.get_next_task(db)

        # Push today's freshly-created sessions up to Google right away
        # rather than waiting for tomorrow's pull-first pass.
        calendar_push = calendar_sync_service.push_pending_sessions(db)

        notifications = notification_service.generate_notifications(db)
        at_risk_count = sum(1 for n in notifications if n.get("type") == "risk")

        narration_input = {
            "scheduled_count": len(scheduled),
            "next_task_title": next_task.title if next_task else None,
            "next_task_deadline": next_task.deadline.isoformat() if next_task and next_task.deadline else None,
            "next_task_estimated_hours": next_task.estimated_hours if next_task else None,
            "at_risk_count": at_risk_count,
        }
        narration, narration_ai_generated = _daily_narration(narration_input)

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_count": len(scheduled),
            "scheduled_task_ids": [t.id for t in scheduled],
            "next_task_id": next_task.id if next_task else None,
            "next_task_title": next_task.title if next_task else None,
            "calendar_sync": calendar_result,
            "calendar_sessions_pushed": calendar_push[0],
            "notifications": notifications,
            "narration": narration,
            "narration_ai_generated": narration_ai_generated,
        }

        setting = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
        if setting is None:
            setting = Setting(key=_SETTINGS_KEY, value=json.dumps(summary))
            db.add(setting)
        else:
            setting.value = json.dumps(summary)
        db.commit()

        logger.info("Morning job: scheduled %d task(s), next up: %s", len(scheduled), next_task.title if next_task else "nothing")
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    # `python -m backend.scheduler.morning` — manual run for testing.
    print(json.dumps(run_morning_job(), indent=2))
