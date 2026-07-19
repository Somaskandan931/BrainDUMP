"""
services/calendar_sync_service.py — Orchestrates Google Calendar <-> the
local CalendarEvent table.

Milestone 6. scheduler_service.generate_free_slots() already reads busy
time from CalendarEvent regardless of source (see its docstring) — this
module's whole job is keeping that table honest against the real Google
Calendar, in both directions:

- pull_google_events(): cache remote events locally as source=GOOGLE rows,
  so the scheduler carves around real meetings/classes without hitting
  the API on every planning run.
- push_pending_sessions(): take source=BRAIN_DUMP rows the scheduler
  already created (sync_status=NOT_SYNCED) and create them on Google, so
  "Assignment — 7-9pm" actually shows up on the user's phone calendar.
- sync_calendar(): the combined pass both the API's POST /sync and the
  morning/nightly jobs call.

Every function here takes a live Session and commits its own work —
same convention as scheduler_service/deadline_service — so callers don't
need to know this module touches the DB.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from backend import config
from backend.integrations import google_calendar
from backend.models.calendar_event import CalendarEvent
from backend.models.enums import EventSource, SyncStatus
from backend.models.task import Task

logger = logging.getLogger(__name__)


def pull_google_events(db: Session, days_ahead: int = None) -> tuple:
    """
    Fetch real Google Calendar events for
    [now - CALENDAR_SYNC_LOOKBACK_DAYS, now + days_ahead] and upsert them
    into CalendarEvent as source=GOOGLE, matched by google_event_id.
    Local GOOGLE rows in that window with no matching remote event
    anymore (deleted/moved on Google's side) are removed. Commits once.
    Returns (pulled_count, removed_count).
    """
    days_ahead = days_ahead or config.SCHEDULING_HORIZON_DAYS
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=config.CALENDAR_SYNC_LOOKBACK_DAYS)
    window_end = now + timedelta(days=days_ahead)

    remote_events = google_calendar.list_events(window_start, window_end)
    remote_by_id = {e["google_event_id"]: e for e in remote_events}

    existing = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.source == EventSource.GOOGLE,
            CalendarEvent.start_time >= window_start,
            CalendarEvent.start_time < window_end,
        )
        .all()
    )
    existing_by_google_id = {e.google_event_id: e for e in existing if e.google_event_id}

    pulled = 0
    for google_event_id, remote in remote_by_id.items():
        row = existing_by_google_id.get(google_event_id)
        if row is None:
            row = CalendarEvent(
                google_event_id=google_event_id,
                title=remote["title"],
                start_time=remote["start"],
                end_time=remote["end"],
                source=EventSource.GOOGLE,
                sync_status=SyncStatus.SYNCED,
                synced=True,
            )
            db.add(row)
        else:
            row.title = remote["title"]
            row.start_time = remote["start"]
            row.end_time = remote["end"]
            row.sync_status = SyncStatus.SYNCED
            row.synced = True
        pulled += 1

    removed = 0
    for google_event_id, row in existing_by_google_id.items():
        if google_event_id not in remote_by_id:
            db.delete(row)
            removed += 1

    db.commit()
    return pulled, removed


def push_pending_sessions(db: Session) -> tuple:
    """
    Push every BRAIN_DUMP CalendarEvent that hasn't reached Google yet
    (sync_status != SYNCED) up as a real event, storing the returned
    google_event_id. Failures are collected rather than aborting the
    whole batch — one bad row shouldn't block the rest of the day's
    schedule from syncing. Commits once at the end. Returns
    (pushed_count, error_messages).
    """
    pending = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.source == EventSource.BRAIN_DUMP, CalendarEvent.sync_status != SyncStatus.SYNCED)
        .all()
    )
    if not pending:
        return 0, []

    pushed = 0
    errors: List[str] = []
    for event in pending:
        try:
            if event.google_event_id:
                google_calendar.update_event(
                    event.google_event_id, title=event.title, start=event.start_time, end=event.end_time
                )
            else:
                event.google_event_id = google_calendar.create_event(
                    event.title, event.start_time, event.end_time
                )
            event.sync_status = SyncStatus.SYNCED
            event.synced = True
            pushed += 1
        except google_calendar.GoogleCalendarError as exc:
            event.sync_status = SyncStatus.ERROR
            errors.append(f"CalendarEvent {event.id} ({event.title!r}): {exc}")
            logger.warning("Failed to push CalendarEvent %d to Google: %s", event.id, exc)

    db.commit()
    return pushed, errors


def push_single_event(db: Session, task: Task, start_time: datetime, end_time: datetime) -> CalendarEvent:
    """
    Create one CalendarEvent immediately and push it to Google right
    away — the "Start Timer on this task right now" path, distinct from
    the batch scheduler which plans ahead over a horizon. Commits once.
    Raises GoogleCalendarError/GoogleCalendarNotConfigured on failure
    without leaving an orphaned local row: the event is only committed
    once the Google push (or the decision to record it as pending)
    succeeds.
    """
    event = CalendarEvent(
        task_id=task.id,
        title=task.title,
        start_time=start_time,
        end_time=end_time,
        source=EventSource.BRAIN_DUMP,
        sync_status=SyncStatus.NOT_SYNCED,
        synced=False,
    )
    try:
        event.google_event_id = google_calendar.create_event(task.title, start_time, end_time)
        event.sync_status = SyncStatus.SYNCED
        event.synced = True
    except google_calendar.GoogleCalendarNotConfigured:
        # Calendar sync isn't set up — still record the session locally
        # (the scheduler already treats BRAIN_DUMP rows as the source of
        # truth for busy time) so the feature degrades, not breaks.
        pass

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def sync_calendar(db: Session, days_ahead: int = None) -> dict:
    """
    Full two-way pass: pull real Google events into the local cache,
    then push any not-yet-synced Brain Dump sessions up to Google. This
    is what POST /api/calendar/sync and the morning/nightly jobs call.
    """
    pulled, removed = pull_google_events(db, days_ahead=days_ahead)
    pushed, push_errors = push_pending_sessions(db)
    return {
        "pulled": pulled,
        "pushed": pushed,
        "removed": removed,
        "errors": push_errors,
    }
