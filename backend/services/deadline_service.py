"""
services/deadline_service.py — Dynamic deadline recalculation.

Milestone 5 responsibilities:
- Detect at-risk tasks: deadline set, but remaining estimated work can't
  fit into the free calendar time actually available before it
- Compress the remaining schedule by wiping not-yet-started future
  CalendarEvents/WorkSessions and repacking from scratch via
  scheduler_service, so a missed day doesn't leave stale, now-wrong
  blocks sitting on the calendar
- When even a full repack can't fit everything before its deadline,
  demote the lowest-importance at-risk tasks (push their deadline out
  rather than silently dropping them) so the compressed schedule is at
  least achievable for what's left
- notification_service.py (later milestone) is where "explain what
  changed and why" surfaces to the user; this module only computes and
  applies the change
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from backend import config
from backend.models.calendar_event import CalendarEvent
from backend.models.enums import Importance, TaskStatus
from backend.models.session import WorkSession
from backend.models.task import Task
from backend.services import scheduler_service


def _active_tasks_with_deadline(db: Session) -> List[Task]:
    return (
        db.query(Task)
        .filter(
            Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS)),
            Task.deadline.isnot(None),
        )
        .all()
    )


def detect_at_risk_tasks(db: Session, now: datetime | None = None) -> List[Task]:
    """
    A task is "at risk" if there isn't enough free calendar time between
    now and its deadline to cover its estimated_hours — checked against
    the *whole* horizon's free capacity, not just this one task's slice
    of it, since that's the honest question ("can this still happen at
    all") even though in practice it'll be competing with other tasks
    for that same time.
    """
    now = now or datetime.now(timezone.utc)
    at_risk: List[Task] = []

    for task in _active_tasks_with_deadline(db):
        deadline = task.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        if deadline <= now:
            at_risk.append(task)
            continue

        days_until = max(1, min(config.SCHEDULING_HORIZON_DAYS, (deadline - now).days + 1))
        free_slots = scheduler_service.generate_free_slots(db, now, horizon_days=days_until)
        free_minutes_before_deadline = sum(
            s.minutes for s in free_slots if s.start < deadline
        )

        needed_hours = task.estimated_hours if task.estimated_hours is not None else config.DEFAULT_TASK_HOURS
        if free_minutes_before_deadline < needed_hours * 60:
            at_risk.append(task)

    return at_risk


def _clear_future_schedule(db: Session, now: datetime) -> None:
    """
    Delete not-yet-started future CalendarEvents/WorkSessions for active
    tasks so compress_schedule() repacks cleanly instead of layering a
    new schedule on top of a stale one. Past/in-progress sessions
    (start_time <= now) are left alone — those already happened or are
    happening, replanning shouldn't erase history.
    """
    future_events = (
        db.query(CalendarEvent)
        .join(Task, Task.id == CalendarEvent.task_id)
        .filter(
            CalendarEvent.start_time > now,
            Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS)),
        )
        .all()
    )
    for event in future_events:
        db.query(WorkSession).filter(WorkSession.calendar_event_id == event.id).delete()
        db.delete(event)
    db.flush()


def demote_task(db: Session, task: Task, push_days: int = 3) -> Task:
    """
    Push a low-priority at-risk task's deadline out rather than dropping
    it, so compress_schedule()'s next pass has a real chance of fitting
    it in. Only ever called on LOW/MEDIUM importance tasks — see
    replan()'s selection below.
    """
    if task.deadline is not None:
        task.deadline = task.deadline + timedelta(days=push_days)
    return task


def compress_schedule(db: Session, now: datetime | None = None) -> List[Task]:
    """
    Wipe the future schedule and repack every active task from scratch,
    tightest-first by priority. Returns the tasks that ended up
    (re)scheduled. This is the "remaining work / remaining days" squeeze:
    since scheduler_service already only offers up real free slots, a
    tighter timeline naturally produces a denser packed schedule with no
    special-casing needed here.
    """
    now = now or datetime.now(timezone.utc)
    _clear_future_schedule(db, now)
    db.commit()
    return scheduler_service.schedule_pending_tasks(db)


def replan(db: Session) -> dict:
    """
    Full replan pass, triggered by POST /api/planner/replan (a missed
    deadline, a slipped day, or just the user asking for a fresh look):

    1. Detect at-risk tasks against the *current* schedule.
    2. Demote LOW/MEDIUM importance at-risk tasks (buy them more runway)
       — HIGH/CRITICAL tasks are left alone; those need to stay visibly
       at-risk rather than have their deadline quietly moved.
    3. Compress: wipe and repack the whole future schedule.
    4. Re-check at-risk status after compression, so the response
       reflects what's still a genuine problem after the squeeze.

    Returns a plain dict (see schemas/planner.py ReplanResponse for the
    API-facing shape) rather than an ORM object, since this is a summary
    of an action taken, not a single persisted row.
    """
    now = datetime.now(timezone.utc)

    at_risk_before = detect_at_risk_tasks(db, now)
    demoted = [
        demote_task(db, t)
        for t in at_risk_before
        if t.importance in (Importance.LOW, Importance.MEDIUM)
    ]
    db.commit()

    rescheduled = compress_schedule(db, now)
    at_risk_after = detect_at_risk_tasks(db, now)

    return {
        "rescheduled_count": len(rescheduled),
        "rescheduled_tasks": rescheduled,
        "demoted_tasks": demoted,
        "at_risk_tasks": at_risk_after,
    }
