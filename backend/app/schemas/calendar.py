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

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from backend.app.models.enums import EventSource, SyncStatus
from backend.app.schemas._mixins import utc_iso


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

    # SQLite hands these back naive (see utils/timeutil.py) — re-attach UTC
    # on the way out so the frontend never misreads them as local time.
    @field_serializer("start_time", "end_time", "created_at", "updated_at")
    def _serialize_utc(self, dt: datetime) -> str:
        return utc_iso(dt)


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


class GoogleConnectionStatus(BaseModel):
    """Whether *this user* has connected Google Calendar (GET /api/calendar/google/status)."""

    oauth_client_configured: bool = Field(
        description="False when the server has no GOOGLE_CALENDAR_CLIENT_ID/SECRET -- connecting is impossible"
    )
    connected: bool


class GoogleConnectResponse(BaseModel):
    """Where to send the user's browser for Google's consent screen."""

    authorization_url: str
