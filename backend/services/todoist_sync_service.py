"""
services/todoist_sync_service.py — Two-way reconciliation between Todoist
and the local Task table.

Milestone 6. Reconciliation is keyed on Task.todoist_id (see
models/task.py):

- pull_todoist_tasks(): remote items with no matching todoist_id become
  new local Tasks; remote items that disappeared (completed/deleted in
  Todoist) mark the matching local Task complete via
  scheduler_service.complete_task() so the ML/estimation loop still
  closes properly.
- push_pending_tasks(): local Tasks with no todoist_id yet (created via
  brain dump, a goal breakdown, or manually) get created on Todoist;
  local Tasks that were just completed but still open on Todoist get
  closed there too.
- sync_todoist(): the combined pass both the API's POST /sync and the
  morning/nightly jobs call.
"""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from backend.integrations import todoist
from backend.models.enums import TaskStatus
from backend.models.task import Task
from backend.services import scheduler_service

logger = logging.getLogger(__name__)


def pull_todoist_tasks(db: Session) -> tuple:
    """
    Import new Todoist items as local Tasks, and complete any local Task
    whose linked Todoist item has disappeared (closed/deleted on
    Todoist's side). Commits once. Returns (pulled_count, errors).
    """
    errors: List[str] = []
    try:
        remote_tasks = todoist.pull_tasks()
    except todoist.TodoistError as exc:
        return 0, [str(exc)]

    remote_ids = {t["todoist_id"] for t in remote_tasks}
    linked_local = db.query(Task).filter(Task.todoist_id.isnot(None)).all()
    linked_by_id = {t.todoist_id: t for t in linked_local}

    pulled = 0
    for remote in remote_tasks:
        if remote["todoist_id"] in linked_by_id:
            continue  # already imported, nothing new to create
        task = Task(
            title=remote["content"],
            deadline=remote["due"],
            importance=todoist.priority_to_importance(remote["priority"]),
            todoist_id=remote["todoist_id"],
        )
        db.add(task)
        pulled += 1

    for todoist_id, local_task in linked_by_id.items():
        if todoist_id not in remote_ids and local_task.status not in (
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        ):
            # Gone from Todoist's active list -> the user completed or
            # deleted it there. Treat as completed rather than
            # cancelled: closing a task is the far more common reason
            # it would vanish from the active list.
            scheduler_service.complete_task(db, local_task)

    db.commit()
    return pulled, errors


def push_pending_tasks(db: Session) -> tuple:
    """
    Create Todoist items for local Tasks that don't have one yet, and
    close the Todoist item for local Tasks that were completed here but
    are still open there. Commits once. Returns (pushed_count, closed_count, errors).
    """
    errors: List[str] = []
    pushed = 0
    closed = 0

    unlinked_active = (
        db.query(Task)
        .filter(
            Task.todoist_id.is_(None),
            Task.status.in_((TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)),
        )
        .all()
    )
    for task in unlinked_active:
        try:
            remote = todoist.push_task(
                task.title,
                due_date=task.deadline,
                priority=todoist.importance_to_priority(task.importance),
                description=task.description,
            )
            task.todoist_id = remote["todoist_id"]
            pushed += 1
        except todoist.TodoistError as exc:
            errors.append(f"Task {task.id} ({task.title!r}): {exc}")
            logger.warning("Failed to push Task %d to Todoist: %s", task.id, exc)

    linked_completed = (
        db.query(Task)
        .filter(Task.todoist_id.isnot(None), Task.status == TaskStatus.COMPLETED)
        .all()
    )
    for task in linked_completed:
        try:
            todoist.close_task(task.todoist_id)
            closed += 1
        except todoist.TodoistError as exc:
            errors.append(f"Task {task.id} ({task.title!r}) close: {exc}")
            logger.warning("Failed to close Task %d on Todoist: %s", task.id, exc)

    db.commit()
    return pushed, closed, errors


def push_single_task(db: Session, task: Task) -> Task:
    """
    Push exactly one Task to Todoist on demand (POST
    /api/todoist/push-task). Raises TodoistError/TodoistNotConfigured on
    failure — the API layer converts those to a clear HTTP status
    rather than silently no-op'ing like the batch sync does.
    """
    remote = todoist.push_task(
        task.title,
        due_date=task.deadline,
        priority=todoist.importance_to_priority(task.importance),
        description=task.description,
    )
    task.todoist_id = remote["todoist_id"]
    db.commit()
    db.refresh(task)
    return task


def sync_todoist(db: Session) -> dict:
    """
    Full two-way pass: pull new/removed Todoist items first (so a task
    completed on the phone doesn't get double-pushed), then push
    whatever's still only local. This is what POST /api/todoist/sync and
    the morning/nightly jobs call.
    """
    pulled, pull_errors = pull_todoist_tasks(db)
    pushed, closed, push_errors = push_pending_tasks(db)
    return {
        "pulled": pulled,
        "pushed": pushed,
        "closed": closed,
        "errors": pull_errors + push_errors,
    }
