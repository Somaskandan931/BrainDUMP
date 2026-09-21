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

Multi-user auth follow-up: every function reads *this session's* user's
personal Todoist API token via services/integration_credentials_service
and passes it into every backend.integrations.todoist call. A user who
hasn't connected Todoist gets TodoistNotConfigured, same as before this
refactor (previously that meant the shared env var was unset; now it
means this particular account has no token saved). New Task rows get
user_id=owner_id(db), same as every other tenant-owned table.
"""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from backend.app.db.database import owner_id
from backend.app.integrations import todoist
from backend.app.models.enums import TaskStatus
from backend.app.models.task import Task
from backend.app.services.integrations import integration_credentials_service
from backend.app.services.planning import scheduler_service
from backend.app.services.workspace.activity_service import ACTOR_SYSTEM

logger = logging.getLogger(__name__)


def pull_todoist_tasks(db: Session) -> tuple:
    """
    Import new Todoist items as local Tasks, and complete any local Task
    whose linked Todoist item has disappeared (closed/deleted on
    Todoist's side). Commits once. Returns (pulled_count, errors).
    """
    api_token = integration_credentials_service.get_todoist_token(db)

    errors: List[str] = []
    try:
        remote_tasks = todoist.pull_tasks(api_token)
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
            user_id=owner_id(db),
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
            scheduler_service.complete_task(db, local_task, actor=ACTOR_SYSTEM)

    db.commit()
    return pulled, errors


def push_pending_tasks(db: Session) -> tuple:
    """
    Create Todoist items for local Tasks that don't have one yet, and
    close the Todoist item for local Tasks that were completed here but
    are still open there. Commits once. Returns (pushed_count, closed_count, errors).
    """
    api_token = integration_credentials_service.get_todoist_token(db)

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
                api_token=api_token,
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
            todoist.close_task(task.todoist_id, api_token=api_token)
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
    api_token = integration_credentials_service.get_todoist_token(db)
    remote = todoist.push_task(
        task.title,
        api_token=api_token,
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
