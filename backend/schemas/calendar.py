"""
schemas/calendar.py — Pydantic schemas for Google Calendar sync endpoints.

Milestone 6. CalendarEventRead mirrors models/calendar_event.py directly;
the sync/create-session request+response shapes are new and only exist
at the API boundary — the actual sync logic lives in
services/calendar_sync_service.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import EventSource, SyncStatus


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: Optional[int]
    google_event_id: Optional[str]
    title: str
    start_time: datetime
    end_time: datetime
    source: EventSource
    sync_status: SyncStatus
    synced: bool
    created_at: datetime
    updated_at: datetime


class CalendarSyncResponse(BaseModel):
    """Result of POST /api/calendar/sync — a two-way pass (pull then push)."""

    pulled: int = Field(description="Google events newly cached/updated locally")
    pushed: int = Field(description="Local Brain Dump sessions newly created on Google")
    removed: int = Field(default=0, description="Locally cached Google events no longer present remotely")
    errors: List[str] = Field(default_factory=list)


class CreateSessionEventRequest(BaseModel):
    """
    Ad hoc "start working on this now" request — e.g. the dashboard's
    Start Timer button — distinct from the batch scheduler's
    pack_tasks_into_schedule(), which runs on a horizon, not on demand.
    """

    task_id: int
    start_time: datetime
    end_time: datetime
