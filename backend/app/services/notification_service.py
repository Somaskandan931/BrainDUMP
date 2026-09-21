"""
services/notification_service.py — Local notifications for plan changes.

PRD §27 (Notification System) is explicit about tone: notifications must
be *actionable* ("help the user make a decision") rather than generic
alerts that "create anxiety". This module was previously a stub with no
implementation at all; every function here corresponds to one of the
four example notifications in §27:

- "Start your next focus session in 10 minutes."      -> upcoming_session_reminders()
- "Today's plan is complete. You have 45 minutes..."  -> free_capacity_notification()
- "Finished earlier than expected. Pull tomorrow's
   work forward?"                                     -> early_finish_notification()
- "Your report deadline is now at risk..."             -> risk_alert_notifications()

generate_notifications() is the single entry point the API route and the
morning/nightly jobs call. Nothing here pushes to an external transport
(email/SMS/OS notification) — this is a local-first, single-user app, so
"notification" means "thing the dashboard/API surfaces right now", not a
delivery pipeline. That's a reasonable place to stop for this milestone;
wiring an actual OS-level notification is a frontend/Electron-Tauri
concern, not a backend one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend import config
from backend.models.calendar_event import CalendarEvent
from backend.models.enums import TaskStatus
from backend.models.task import Task
from backend.services import deadline_service, scheduler_service

UPCOMING_SESSION_WINDOW_MINUTES = 15


@dataclass
class Notification:
    type: str
    severity: str
    message: str
    task_id: Optional[int] = None
    action: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "task_id": self.task_id,
            "action": self.action,
        }


def upcoming_session_reminders(db: Session, now: Optional[datetime] = None) -> List[Notification]:
    now = now or datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=UPCOMING_SESSION_WINDOW_MINUTES)

    upcoming = (
        db.query(CalendarEvent)
        .join(Task, Task.id == CalendarEvent.task_id)
        .filter(
            CalendarEvent.start_time > now,
            CalendarEvent.start_time <= window_end,
            Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS)),
        )
        .order_by(CalendarEvent.start_time)
        .all()
    )

    notifications = []
    for event in upcoming:
        start = event.start_time if event.start_time.tzinfo else event.start_time.replace(tzinfo=timezone.utc)
        minutes_away = max(1, round((start - now).total_seconds() / 60))
        notifications.append(
            Notification(
                type="reminder",
                severity="info",
                message=f"Start your next focus session — {event.title} — in {minutes_away} minutes.",
                task_id=event.task_id,
                action="start_session",
            )
        )
    return notifications


def free_capacity_notification(db: Session, now: Optional[datetime] = None) -> Optional[Notification]:
    now = now or datetime.now(timezone.utc)
    end_of_day = now.replace(hour=config.WORK_DAY_END_HOUR, minute=0, second=0, microsecond=0)
    if now >= end_of_day:
        return None

    remaining_today = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.start_time >= now, CalendarEvent.start_time < end_of_day)
        .count()
    )
    if remaining_today > 0:
        return None

    free_slots = scheduler_service.generate_free_slots(db, now, horizon_days=1)
    free_minutes = sum(s.minutes for s in free_slots if s.start < end_of_day)
    if free_minutes < config.MIN_SLOT_MINUTES:
        return None

    return Notification(
        type="capacity",
        severity="info",
        message=f"Today's plan is complete. You have {int(free_minutes)} minutes of free capacity.",
        action="pull_tomorrow_forward",
    )


def early_finish_notification(db: Session, now: Optional[datetime] = None) -> Optional[Notification]:
    now = now or datetime.now(timezone.utc)

    recently_completed = (
        db.query(Task)
        .join(CalendarEvent, CalendarEvent.task_id == Task.id)
        .filter(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at.isnot(None),
            Task.completed_at >= now - timedelta(hours=1),
            CalendarEvent.end_time > now,
        )
        .first()
    )
    if recently_completed is None:
        return None

    return Notification(
        type="pull_forward",
        severity="info",
        message="You've finished earlier than expected. Shall I pull tomorrow's work forward?",
        task_id=recently_completed.id,
        action="pull_tomorrow_forward",
    )


def risk_alert_notifications(db: Session, now: Optional[datetime] = None) -> List[Notification]:
    now = now or datetime.now(timezone.utc)
    at_risk = deadline_service.detect_at_risk_tasks(db, now)

    notifications = []
    for task in at_risk:
        label = task.title if len(task.title) <= 60 else task.title[:57] + "..."
        notifications.append(
            Notification(
                type="risk",
                severity="warning",
                message=f"Your \"{label}\" deadline is now at risk based on today's schedule.",
                task_id=task.id,
                action="review_task",
            )
        )
    return notifications


def generate_notifications(db: Session, now: Optional[datetime] = None) -> List[dict]:
    now = now or datetime.now(timezone.utc)

    notifications: List[Notification] = []
    notifications.extend(risk_alert_notifications(db, now))
    notifications.extend(upcoming_session_reminders(db, now))

    early_finish = early_finish_notification(db, now)
    if early_finish is not None:
        notifications.append(early_finish)

    capacity = free_capacity_notification(db, now)
    if capacity is not None:
        notifications.append(capacity)

    return [n.to_dict() for n in notifications]
