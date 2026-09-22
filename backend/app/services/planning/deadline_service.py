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

from backend.app.core import config
from backend.app.ai import episodic_memory
from backend.app.db.database import owner_id
from backend.app.models.calendar_event import CalendarEvent
from backend.app.models.enums import EpisodicEventType, Importance, TaskStatus
from backend.app.services.workspace.activity_service import log_activity
from backend.app.models.session import WorkSession
from backend.app.models.task import Task
from backend.app.services.planning import scheduler_service
from backend.app.utils.timeutil import ensure_utc


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


def demote_task(db: Session, task: Task, push_days: int = 3, actor: str = "user") -> Task:
    """
    Push a low-priority at-risk task's deadline out rather than dropping
    it, so compress_schedule()'s next pass has a real chance of fitting
    it in. Only ever called on LOW/MEDIUM importance tasks — see
    replan()'s selection below.

    Logs task.deadline_pushed with the reason, whether it was already
    overdue, and the exact before/after dates -- this is the data behind
    GET /api/tasks/{id}/history's "why did BrainDUMP move this task?".
    """
    if task.deadline is not None:
        old_deadline = ensure_utc(task.deadline)
        was_overdue = old_deadline < datetime.now(timezone.utc)
        task.deadline = old_deadline + timedelta(days=push_days)
        importance = task.importance.value if hasattr(task.importance, "value") else str(task.importance)
        log_activity(
            db, user_id=owner_id(db), action="task.deadline_changed", entity_type="task", entity_id=task.id,
            actor=actor,
            details={
                "reason": "at_risk_demoted",
                "importance": importance,
                "was_overdue": was_overdue,
                "push_days": push_days,
                "from": old_deadline.isoformat(),
                "to": task.deadline.isoformat(),
            },
        )
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


def persist_deadline_plan(db: Session, task: Task, plan: Optional[dict] = None) -> Task:
    """
    Compute (if not already given) and persist the Deadline Engine's
    outputs onto the task row itself: recommended_deadline (the
    "default"-buffer target), latest_safe_start (target minus the hours
    of work remaining), risk_score, and completion_probability. Without
    this, PRD §72's Deadline Engine acceptance criteria ("risk score is
    shown", "a realistic completion time is generated") had nothing to
    read from besides recomputing compute_deadline_plan() ad hoc — the
    values never survived past a single request/response.
    """
    if task.deadline is None:
        return task

    plan = plan or compute_deadline_plan(db, task)
    default_buffer = next((b for b in plan["buffers"] if b["level"] == "default"), None)
    if default_buffer is None:
        return task

    target = default_buffer["target_date"]
    hours_needed = default_buffer["hours_needed"]
    task.recommended_deadline = target
    task.latest_safe_start = target - timedelta(hours=hours_needed) if hours_needed else target

    status_to_risk = {"safe": 0.15, "tight": 0.55, "impossible": 0.9, "done": 0.0}
    task.risk_score = status_to_risk.get(default_buffer["status"], 0.5)
    task.completion_probability = round(1.0 - task.risk_score, 2)

    return task


def replan(db: Session, actor: str = "user") -> dict:
    """
    Full replan pass, triggered by POST /api/planner/replan (a missed
    deadline, a slipped day, or just the user asking for a fresh look)
    or by the nightly job (actor="system"):

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

    Each demoted task already gets its own task.deadline_pushed row (see
    demote_task above); this additionally logs one schedule.replanned
    row per pass with the ids of everything repacked -- a row per
    repacked task every night would grow the activity table by O(active
    tasks) per user per night for no real benefit, since "which slot did
    this land in" isn't itself a deadline change.
    """
    now = datetime.now(timezone.utc)

    at_risk_before = detect_at_risk_tasks(db, now)
    demoted = [
        demote_task(db, t, actor=actor)
        for t in at_risk_before
        if t.importance in (Importance.LOW, Importance.MEDIUM)
    ]
    db.commit()

    rescheduled = compress_schedule(db, now)
    at_risk_after = detect_at_risk_tasks(db, now)

    for task in _active_tasks_with_deadline(db):
        persist_deadline_plan(db, task)

    if demoted or rescheduled:
        log_activity(
            db, user_id=owner_id(db), action="schedule.replanned", entity_type="schedule", actor=actor,
            details={
                "rescheduled_task_ids": [t.id for t in rescheduled],
                "demoted_task_ids": [t.id for t in demoted],
                "at_risk_after_count": len(at_risk_after),
            },
        )
    db.commit()

    _record_replan_episode(db, now=now, demoted=demoted, rescheduled=rescheduled, at_risk_after=at_risk_after)

    return {
        "rescheduled_count": len(rescheduled),
        "rescheduled_tasks": rescheduled,
        "demoted_tasks": demoted,
        "at_risk_tasks": at_risk_after,
    }


def _record_replan_episode(
    db: Session, *, now: datetime, demoted: List[Task], rescheduled: List[Task], at_risk_after: List[Task]
) -> None:
    """
    Episodic Memory (PRD §63 "Planning decisions"): replan() runs both
    from the nightly job (every night) and from an explicit user request,
    so this only records something when the pass actually changed the
    plan -- a quiet night with nothing to compress isn't a planning
    decision worth remembering. occurred_on is today's date, so at most
    one row per day gets written/updated even if replan() is triggered
    more than once (e.g. nightly job + a manual replan the same day) --
    record_event()'s dedup on (type, date, title) collapses those into
    one, with the later call's summary winning.
    """
    if not demoted and not rescheduled:
        return
    parts = []
    if rescheduled:
        parts.append(f"repacked {len(rescheduled)} task(s)")
    if demoted:
        parts.append(f"pushed out {len(demoted)} lower-priority task(s)")
    if at_risk_after:
        parts.append(f"{len(at_risk_after)} still at risk")
    summary = "Replan: " + ", ".join(parts) + "."
    episodic_memory.record_event(
        db,
        EpisodicEventType.PLANNING_DECISION,
        title=f"Replan: {now.date().isoformat()}",
        summary=summary,
        occurred_on=now.date(),
        payload={
            "rescheduled_task_ids": [t.id for t in rescheduled],
            "demoted_task_ids": [t.id for t in demoted],
            "at_risk_task_ids": [t.id for t in at_risk_after],
        },
    )