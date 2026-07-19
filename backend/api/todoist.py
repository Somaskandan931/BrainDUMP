"""
api/todoist.py — Todoist sync endpoints.

Milestone 6: real endpoints backed by backend/integrations/todoist.py and
backend/services/todoist_sync_service.py. Unlike Google Calendar, a
missing/invalid Todoist token doesn't need a distinct 424 status for the
batch /sync endpoint — todoist_sync_service already collects that as an
`errors` entry in the 200 response, since a partial sync (calendar half
working, Todoist not configured) is a normal state, not a request
failure. The single push-task endpoint below is the exception: an
explicit "push this one task" ask should fail loudly if it can't happen.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.integrations.todoist import TodoistError, TodoistNotConfigured
from backend.models.task import Task
from backend.schemas.todoist import (
    PushTaskRequest,
    PushTaskResponse,
    TodoistSyncResponse,
    TodoistTaskRead,
)
from backend.services import todoist_sync_service
from backend.integrations import todoist as todoist_client

router = APIRouter()


@router.get("/tasks", response_model=List[TodoistTaskRead])
def list_todoist_tasks() -> List[TodoistTaskRead]:
    """Live read-through to Todoist's active items — not the local cache."""
    try:
        remote_tasks = todoist_client.pull_tasks()
    except TodoistNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc)) from exc
    except TodoistError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [TodoistTaskRead(**t) for t in remote_tasks]


@router.post("/sync", response_model=TodoistSyncResponse)
def sync_todoist(db: Session = Depends(get_db)) -> TodoistSyncResponse:
    """
    Two-way sync: import new/removed Todoist items first, then push
    whatever Brain Dump tasks are still only local. Always 200 — a
    missing token surfaces as an `errors` entry, not a failed request,
    since Todoist sync is one of two independent integrations this
    endpoint's sibling (/api/calendar/sync) doesn't depend on.
    """
    result = todoist_sync_service.sync_todoist(db)
    return TodoistSyncResponse(**result)


@router.post("/push-task", response_model=PushTaskResponse)
def push_task(payload: PushTaskRequest, db: Session = Depends(get_db)) -> PushTaskResponse:
    """Push exactly one task to Todoist on demand. Fails loudly, unlike batch /sync."""
    task = db.get(Task, payload.task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.todoist_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task {task.id} is already linked to Todoist item {task.todoist_id}",
        )

    try:
        updated = todoist_sync_service.push_single_task(db, task)
    except TodoistNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc)) from exc
    except TodoistError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return PushTaskResponse(task_id=updated.id, todoist_id=updated.todoist_id)
