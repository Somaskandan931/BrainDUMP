"""
api/calendar.py — Google Calendar sync endpoints.

Milestone 6: real endpoints backed by backend/integrations/google_calendar.py
and backend/services/calendar_sync_service.py. If credentials.json isn't
present yet (the one-time OAuth app setup hasn't been done), these return
424 Failed Dependency with setup instructions rather than a 500 — this is
a local config gap, not a server bug. See INTEGRATIONS.md.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.integrations.google_calendar import GoogleCalendarError, GoogleCalendarNotConfigured
from backend.models.calendar_event import CalendarEvent
from backend.models.enums import EventSource
from backend.models.task import Task
from backend.schemas.calendar import CalendarEventRead, CalendarSyncResponse, CreateSessionEventRequest
from backend.services import calendar_sync_service

router = APIRouter()


@router.get("/events", response_model=List[CalendarEventRead])
def list_events(
    source: Optional[EventSource] = None, db: Session = Depends(get_db)
) -> List[CalendarEvent]:
    """
    Locally cached calendar events (both source=BRAIN_DUMP scheduler
    blocks and source=GOOGLE events pulled in by /sync). Reads the local
    cache only — call POST /sync first to refresh it against Google.
    """
    query = db.query(CalendarEvent)
    if source is not None:
        query = query.filter(CalendarEvent.source == source)
    return query.order_by(CalendarEvent.start_time).all()


@router.post("/sync", response_model=CalendarSyncResponse)
def sync_calendar(db: Session = Depends(get_db)) -> CalendarSyncResponse:
    """
    Two-way sync: pull real Google Calendar events into the local cache,
    then push any Brain Dump work sessions the scheduler created that
    haven't reached Google yet.
    """
    try:
        result = calendar_sync_service.sync_calendar(db)
    except GoogleCalendarNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc)) from exc
    except GoogleCalendarError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return CalendarSyncResponse(**result)


@router.post("/create-session", response_model=CalendarEventRead)
def create_session_event(
    payload: CreateSessionEventRequest, db: Session = Depends(get_db)
) -> CalendarEvent:
    """
    Create an ad hoc work session for a task right now (e.g. the
    dashboard's Start Timer button) and push it straight to Google —
    distinct from the batch scheduler, which plans ahead over a horizon
    in services/scheduler_service.py.
    """
    task = db.get(Task, payload.task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if payload.end_time <= payload.start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_time must be after start_time"
        )

    try:
        return calendar_sync_service.push_single_event(db, task, payload.start_time, payload.end_time)
    except GoogleCalendarError as exc:
        # Note: GoogleCalendarNotConfigured is caught inside push_single_event
        # itself (the session is still recorded locally) — only a genuine
        # API failure reaches here.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
