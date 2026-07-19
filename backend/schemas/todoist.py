"""
schemas/todoist.py — Pydantic schemas for Todoist sync endpoints.

Milestone 6. TodoistTaskRead is a read-only view of a remote Todoist
item (not a Brain Dump Task — see services/todoist_sync_service.py for
how the two get reconciled); the sync/push-task shapes are the API
boundary around that reconciliation logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TodoistTaskRead(BaseModel):
    todoist_id: str
    content: str
    due: Optional[datetime] = None
    priority: int


class TodoistSyncResponse(BaseModel):
    """Result of POST /api/todoist/sync — a two-way pass (pull then push)."""

    pulled: int = Field(description="Todoist items imported as new Brain Dump tasks")
    pushed: int = Field(description="Brain Dump tasks newly created on Todoist")
    closed: int = Field(default=0, description="Todoist items closed because the local task was completed")
    errors: List[str] = Field(default_factory=list)


class PushTaskRequest(BaseModel):
    task_id: int


class PushTaskResponse(BaseModel):
    task_id: int
    todoist_id: str
