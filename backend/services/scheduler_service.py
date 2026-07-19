"""
services/scheduler_service.py — Turns prioritized tasks into calendar work sessions.

Milestone 5 responsibilities:
- Compute free/busy slots from locally-stored CalendarEvents (Google
  Calendar's *real* API wrapper is Milestone 6 — until then, CalendarEvent
  rows created here with source=BRAIN_DUMP already double as the local
  calendar, per models/calendar_event.py's design)
- Pack tasks into those slots respecting working hours + priority order
- Resolve conflicts by simply not double-booking: once a slot is consumed
  it's gone for the rest of this scheduling pass

Every task this module schedules gets a CalendarEvent (the calendar block)
and a matching WorkSession (the session record ml/estimator.py will later
train on, once actual_hours gets filled in at completion).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend import config
from backend.ml import estimator
from backend.ml.priority_model import compute_priority_score, compute_context_switch_cost
from backend.models.calendar_event import CalendarEvent
from backend.models.enums import EventSource, SyncStatus, TaskStatus
from backend.models.session import WorkSession
from backend.models.task import Task


@dataclass
class Slot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0


def _active_statuses() -> tuple:
    return (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)


def get_busy_intervals(db: Session, start: datetime, end: datetime) -> List[Tuple[datetime, datetime]]:
    """All CalendarEvents (any source) overlapping [start, end), sorted by start."""
    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.end_time > start, CalendarEvent.start_time < end)
        .order_by(CalendarEvent.start_time)
        .all()
    )
    # SQLite round-trips DateTime(timezone=True) columns as naive datetimes
    # (no tz info survives the string storage) — every other datetime this
    # module works with is UTC-aware, so normalize here rather than at
    # every comparison site downstream.
    return [(_as_utc(e.start_time), _as_utc(e.end_time)) for e in events]


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def generate_free_slots(
    db: Session,
    start: datetime,
    horizon_days: int = config.SCHEDULING_HORIZON_DAYS,
) -> List[Slot]:
    """
    Free working-hour slots from `start` through `horizon_days` ahead,
    with existing CalendarEvents carved out. Slots never start in the
    past relative to `start`.
    """
    end = start + timedelta(days=horizon_days)
    busy = get_busy_intervals(db, start, end)

    slots: List[Slot] = []
    current_day = start.date()
    last_day = end.date()

    while current_day <= last_day:
        day_start = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc).replace(
            hour=config.WORK_DAY_START_HOUR
        )
        day_end = datetime.combine(current_day, datetime.min.time(), tzinfo=timezone.utc).replace(
            hour=config.WORK_DAY_END_HOUR
        )
        day_start = max(day_start, start)

        if day_start < day_end:
            slots.extend(_carve_busy(day_start, day_end, busy))

        current_day += timedelta(days=1)

    return [s for s in slots if s.minutes >= config.MIN_SLOT_MINUTES]


def _carve_busy(
    window_start: datetime, window_end: datetime, busy: List[Tuple[datetime, datetime]]
) -> List[Slot]:
    """Subtract every busy interval overlapping [window_start, window_end) from that window."""
    relevant = sorted(
        (b_start, b_end) for b_start, b_end in busy if b_end > window_start and b_start < window_end
    )

    slots: List[Slot] = []
    cursor = window_start
    for b_start, b_end in relevant:
        b_start = max(b_start, window_start)
        b_end = min(b_end, window_end)
        if b_start > cursor:
            slots.append(Slot(cursor, b_start))
        cursor = max(cursor, b_end)

    if cursor < window_end:
        slots.append(Slot(cursor, window_end))

    return slots


def pack_tasks_into_schedule(
    db: Session, tasks: List[Task], slots: List[Slot]
) -> List[Tuple[Task, CalendarEvent, WorkSession]]:
    """
    Greedily assign each task (already priority-ordered) to the earliest
    free slot with enough room, consuming that much time from the slot
    (splitting it if there's leftover). Tasks that don't fit anywhere in
    `slots` are skipped, not force-scheduled. Does not commit.
    """
    remaining_slots = [Slot(s.start, s.end) for s in slots]
    scheduled: List[Tuple[Task, CalendarEvent, WorkSession]] = []

    for task in tasks:
        hours = task.estimated_hours if task.estimated_hours is not None else config.DEFAULT_TASK_HOURS
        needed_minutes = max(hours * 60, config.MIN_SLOT_MINUTES)

        chosen_index: Optional[int] = None
        for i, slot in enumerate(remaining_slots):
            if slot.minutes >= needed_minutes:
                chosen_index = i
                break
        if chosen_index is None:
            continue  # doesn't fit anywhere in the horizon — left for the next replan

        slot = remaining_slots[chosen_index]
        block_start = slot.start
        block_end = block_start + timedelta(minutes=needed_minutes)

        event = CalendarEvent(
            task_id=task.id,
            title=task.title,
            start_time=block_start,
            end_time=block_end,
            source=EventSource.BRAIN_DUMP,
            sync_status=SyncStatus.NOT_SYNCED,
            synced=False,
        )
        db.add(event)
        db.flush()  # assigns event.id for the WorkSession FK below

        session = WorkSession(
            task_id=task.id,
            calendar_event_id=event.id,
            start_time=block_start,
            end_time=block_end,
            predicted_duration_minutes=int(needed_minutes),
        )
        db.add(session)

        remainder = Slot(block_end, slot.end)
        if remainder.minutes >= config.MIN_SLOT_MINUTES:
            remaining_slots[chosen_index] = remainder
        else:
            remaining_slots.pop(chosen_index)

        scheduled.append((task, event, session))

    return scheduled


def _score_and_order_tasks(db: Session, tasks: List[Task], now: datetime) -> List[Task]:
    """
    Score every task (ignoring context switching on the first pass, since
    order isn't known yet), sort descending, then walk the sorted list
    once more filling in each task's real context_switch_cost against
    whichever task now precedes it — and folding that into the final
    stored priority_score.
    """
    for task in tasks:
        task.priority_score = compute_priority_score(task, now=now)
    tasks.sort(key=lambda t: (t.priority_score or 0.0), reverse=True)

    previous: Optional[Task] = None
    for task in tasks:
        switch_cost = compute_context_switch_cost(task, previous)
        task.context_switch_cost = switch_cost
        task.priority_score = compute_priority_score(
            task, now=now, context_switch_cost=switch_cost
        )
        previous = task

    tasks.sort(key=lambda t: (t.priority_score or 0.0), reverse=True)
    return tasks


def schedule_pending_tasks(
    db: Session, horizon_days: int = config.SCHEDULING_HORIZON_DAYS
) -> List[Task]:
    """
    Full orchestration: pick up every active task that isn't already
    scheduled into a future CalendarEvent, estimate/prioritize it, and
    pack it into free slots over the next `horizon_days`. Commits once.
    Returns the tasks that were newly scheduled.
    """
    now = datetime.now(timezone.utc)

    already_scheduled_task_ids = {
        row[0]
        for row in db.query(CalendarEvent.task_id)
        .filter(CalendarEvent.task_id.isnot(None), CalendarEvent.start_time >= now)
        .all()
    }

    candidates = (
        db.query(Task)
        .filter(Task.status.in_(_active_statuses()))
        .filter(~Task.id.in_(already_scheduled_task_ids) if already_scheduled_task_ids else True)
        .all()
    )
    if not candidates:
        return []

    for task in candidates:
        estimator.ensure_estimate(db, task, log=True)

    ordered = _score_and_order_tasks(db, candidates, now)
    slots = generate_free_slots(db, now, horizon_days)
    scheduled = pack_tasks_into_schedule(db, ordered, slots)

    db.commit()
    result = [task for task, _event, _session in scheduled]
    for task in result:
        db.refresh(task)
    return result


def complete_task(db: Session, task: Task) -> Task:
    """
    Mark `task` complete and close the loop with the ML layer: if the
    user never set actual_hours by hand, sum the WorkSessions scheduled
    against this task as a best-effort actual duration, then resolve any
    pending Prediction so ml/trainer.py (Milestone 8) has real (predicted,
    actual) pairs to eventually train on. Commits once.

    Milestone 5 moves this out of api/tasks.py per the plan noted there:
    multi-step operations belong in services/, routes stay thin.
    """
    from datetime import datetime, timezone

    from backend.ml import estimator
    from backend.models.enums import TaskStatus

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)

    if task.actual_hours is None:
        total_minutes = sum(s.duration_minutes or 0 for s in task.sessions)
        if total_minutes > 0:
            task.actual_hours = round(total_minutes / 60.0, 2)

    estimator.resolve_prediction(db, task)

    db.commit()
    db.refresh(task)
    return task


def get_next_task(db: Session) -> Optional[Task]:
    """
    The single 'Do Next' task: highest priority_score among active tasks,
    scored fresh against right now (not the last time schedule_pending_tasks
    ran), with context switching computed against whatever the user most
    recently completed — so the recommendation reflects momentum, not just
    a stale batch score.
    """
    now = datetime.now(timezone.utc)

    candidates = db.query(Task).filter(Task.status.in_(_active_statuses())).all()
    if not candidates:
        return None

    last_completed = (
        db.query(Task)
        .filter(Task.status == TaskStatus.COMPLETED)
        .order_by(Task.completed_at.desc())
        .first()
    )

    for task in candidates:
        estimator.ensure_estimate(db, task, log=False)
        switch_cost = compute_context_switch_cost(task, last_completed)
        task.context_switch_cost = switch_cost
        task.priority_score = compute_priority_score(
            task, now=now, context_switch_cost=switch_cost
        )

    db.commit()

    best = max(
        candidates,
        key=lambda t: (
            t.priority_score or 0.0,
            -(t.deadline.timestamp() if t.deadline else float("inf")),
        ),
    )
    db.refresh(best)
    return best
