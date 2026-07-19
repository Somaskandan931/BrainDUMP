"""
scheduler/morning.py — Morning job (runs ~7 AM via APScheduler, see app.py).

Milestone 5 implementation:
1. schedule_pending_tasks() packs any not-yet-scheduled active tasks into
   free slots, reading busy time from the CalendarEvent table.
2. get_next_task() computes today's single "Do Next" recommendation.

Milestone 6 adds real Google Calendar + Todoist sync around that core:
0. Pull real Google Calendar events first, so step 1 above carves around
   actual meetings/classes, not just previously-scheduled Brain Dump
   sessions.
3. Push today's newly scheduled sessions to Google Calendar and sync
   Todoist (pull new/removed items, push anything still local-only).
   Both are wrapped in try/except: an unconfigured integration (no
   credentials.json / no TODOIST_API_TOKEN yet) degrades the morning job
   to "just don't sync that one thing" rather than failing the whole run.

Everything is written to the settings table under "last_morning_summary"
as the dashboard payload (Milestone 7 reads it; there's no dashboard API
yet, so this is where that payload lives for now instead of being
silently discarded).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.database import SessionLocal
from backend.integrations.google_calendar import GoogleCalendarError
from backend.integrations.todoist import TodoistError
from backend.models.settings import Setting
from backend.services import calendar_sync_service, scheduler_service, todoist_sync_service

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "last_morning_summary"


def _try_sync_calendar(db) -> dict:
    try:
        return calendar_sync_service.sync_calendar(db)
    except GoogleCalendarError as exc:
        logger.info("Morning job: Google Calendar sync skipped (%s)", exc)
        return {"pulled": 0, "pushed": 0, "removed": 0, "errors": [str(exc)]}


def _try_sync_todoist(db) -> dict:
    try:
        return todoist_sync_service.sync_todoist(db)
    except TodoistError as exc:
        logger.info("Morning job: Todoist sync skipped (%s)", exc)
        return {"pulled": 0, "pushed": 0, "closed": 0, "errors": [str(exc)]}


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
        todoist_result = _try_sync_todoist(db)

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_count": len(scheduled),
            "scheduled_task_ids": [t.id for t in scheduled],
            "next_task_id": next_task.id if next_task else None,
            "next_task_title": next_task.title if next_task else None,
            "calendar_sync": calendar_result,
            "calendar_sessions_pushed": calendar_push[0],
            "todoist_sync": todoist_result,
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
