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
from typing import List, Optional

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


def _buffer_target(deadline: datetime, buffer_days: int) -> datetime:
    """Aggressive (0-day buffer) is the deadline itself; others pull earlier."""
    return deadline - timedelta(days=buffer_days)


def _free_hours_before(db: Session, now: datetime, target: datetime) -> float:
    """
    Free calendar hours between `now` and `target`, reusing the same
    slot-generation logic the scheduler and at-risk detection use — so
    "can I actually fit this" means the same thing everywhere in the app.
    """
    if target <= now:
        return 0.0

    horizon_days = min(
        config.DEADLINE_PLAN_MAX_HORIZON_DAYS,
        (target - now).days + config.DEADLINE_PLAN_LOOKAHEAD_PADDING_DAYS,
    )
    free_slots = scheduler_service.generate_free_slots(db, now, horizon_days=horizon_days)
    free_minutes = sum(s.minutes for s in free_slots if s.start < target)
    return free_minutes / 60.0


def _buffer_status(hours_needed: float, free_hours: float) -> str:
    if hours_needed <= 0:
        return "done"
    ratio = free_hours / hours_needed
    if ratio >= config.DEADLINE_SAFE_RATIO:
        return "safe"
    if ratio >= config.DEADLINE_TIGHT_RATIO:
        return "tight"
    return "impossible"


def _buffer_message(level: str, target: datetime, status: str, daily_hours: Optional[float]) -> str:
    target_label = target.strftime("%b %d")
    if status == "done":
        return "Already done — nothing left to schedule."
    if status == "impossible":
        return f"Not enough free time before {target_label} at this buffer — something else needs to move."
    if level == "aggressive":
        return f"Complete by {target.strftime('%b %d, %I:%M %p')}"
    daily = f" · ~{daily_hours:.1f}h/day" if daily_hours else ""
    return f"Complete before {target_label}{daily}"


def compute_deadline_plan(db: Session, task: Task, now: datetime | None = None) -> dict:
    """
    The Deadline Engine: for a task with a deadline, compute three target
    completion dates (safe / default / aggressive) and whether the user's
    actual free calendar time can support each one. `estimated_hours`
    minus any already-logged `actual_hours` is treated as the remaining
    work — a task that's partly done needs less runway than a fresh one.
    """
    if task.deadline is None:
        raise ValueError("compute_deadline_plan requires a task with a deadline")

    now = now or datetime.now(timezone.utc)
    deadline = task.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    estimated = task.estimated_hours if task.estimated_hours is not None else config.DEFAULT_TASK_HOURS
    hours_remaining = max(0.0, estimated - (task.actual_hours or 0.0))

    buffers = []
    for level, buffer_days in config.DEADLINE_BUFFER_DAYS.items():
        target = _buffer_target(deadline, buffer_days)
        days_remaining = max(0.0, (target - now).total_seconds() / 86400.0)
        free_hours = _free_hours_before(db, now, target)
        status = _buffer_status(hours_remaining, free_hours)
        daily_hours = (hours_remaining / days_remaining) if days_remaining > 0 else hours_remaining

        buffers.append(
            {
                "level": level,
                "target_date": target,
                "days_remaining": round(days_remaining, 2),
                "free_hours_available": round(free_hours, 2),
                "hours_needed": round(hours_remaining, 2),
                "suggested_daily_hours": round(daily_hours, 2) if daily_hours else None,
                "status": status,
                "message": _buffer_message(level, target, status, daily_hours),
            }
        )

    # Aggressive first (nearest target) through safe last (furthest out) —
    # matches how the frontend reads it top-to-bottom, most urgent first.
    order = {"aggressive": 0, "default": 1, "safe": 2}
    buffers.sort(key=lambda b: order[b["level"]])

    return {
        "task_id": task.id,
        "title": task.title,
        "deadline": deadline,
        "estimated_hours": task.estimated_hours,
        "hours_remaining": round(hours_remaining, 2),
        "buffers": buffers,
    }


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
