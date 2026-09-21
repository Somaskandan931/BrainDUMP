"""
api/calendar.py — Google Calendar sync endpoints.

Milestone 6: real endpoints backed by backend/integrations/google_calendar.py
and backend/services/calendar_sync_service.py. If the server's OAuth client
isn't configured, or this user hasn't connected their calendar yet, the sync
endpoints return 424 Failed Dependency with setup instructions rather than a
500 — this is a config/opt-in gap, not a server bug. See INTEGRATIONS.md.

Multi-user auth follow-up: each user connects their own Google account.
GET /google/connect (authenticated) returns the consent-screen URL, with a
short-lived signed `state` naming the user; Google then redirects the browser
to GET /google/callback, which has no Authorization header of its own, so it
identifies the user from that `state` alone, stores their credentials, and
bounces the browser back to the frontend's Settings page.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.api.v1.deps import get_current_user, get_scoped_db
from backend.app.auth import security
from backend.app.db.database import SessionLocal
from backend.app.integrations import google_calendar
from backend.app.integrations.google_calendar import GoogleCalendarError, GoogleCalendarNotConfigured
from backend.app.models.calendar_event import CalendarEvent
from backend.app.models.enums import EventSource
from backend.app.models.task import Task
from backend.app.models.user import User
from backend.app.schemas.calendar import (
    CalendarEventRead,
    CalendarSyncResponse,
    CreateSessionEventRequest,
    GoogleConnectionStatus,
    GoogleConnectResponse,
)
from backend.app.db.database import owner_id
from backend.app.services.integrations import calendar_sync_service, integration_credentials_service
from backend.app.services.workspace.activity_service import log_activity

logger = logging.getLogger(__name__)

router = APIRouter()

# The `purpose` claim on the OAuth `state` token -- see auth/security.py.
_OAUTH_STATE_PURPOSE = "google_calendar_oauth"


# ---------------------------------------------------------------------------
# Connect / disconnect (per-user Google OAuth)
# ---------------------------------------------------------------------------

@router.get("/google/status", response_model=GoogleConnectionStatus)
def google_status(db: Session = Depends(get_scoped_db)) -> GoogleConnectionStatus:
    return GoogleConnectionStatus(
        oauth_client_configured=google_calendar.is_oauth_client_configured(),
        connected=integration_credentials_service.has_google_credentials(db),
    )


@router.get("/google/connect", response_model=GoogleConnectResponse)
def google_connect(current_user: User = Depends(get_current_user)) -> GoogleConnectResponse:
    """
    Start the OAuth flow. Authenticated (the SPA calls it with the user's
    bearer token and then navigates the browser to the returned URL) --
    a plain redirect route couldn't be, since a browser navigation can't
    carry an Authorization header.
    """
    state = security.create_state_token(current_user.id, _OAUTH_STATE_PURPOSE)
    try:
        url = google_calendar.build_authorization_url(state)
    except GoogleCalendarNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc)) from exc
    return GoogleConnectResponse(authorization_url=url)


@router.get("/google/callback", include_in_schema=False)
def google_callback(
    code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None
) -> RedirectResponse:
    """
    Google redirects the browser here after the consent screen. There's no
    bearer token on this request, so the user is identified purely by the
    signed `state` from /google/connect. Always ends in a redirect back to
    the frontend's Settings page (?calendar=connected | ?calendar=error) --
    this is a browser navigation, not an API call, so a JSON error body
    would just strand the user on a blank page.
    """

    def _back(outcome: str) -> RedirectResponse:
        return RedirectResponse(f"{config.FRONTEND_URL.rstrip('/')}/settings?calendar={outcome}", status_code=303)

    if error or not code or not state:
        logger.info("Google Calendar OAuth callback without a usable code (error=%r)", error)
        return _back("error")

    user_id = security.decode_state_token(state, _OAUTH_STATE_PURPOSE)
    if user_id is None:
        logger.warning("Google Calendar OAuth callback with an invalid/expired/foreign state token")
        return _back("error")

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return _back("error")
        db.info["user_id"] = user_id  # the same by-hand scoping the background jobs use

        credentials_json = google_calendar.exchange_code(code)
        if not json.loads(credentials_json).get("refresh_token"):
            # Without a refresh token the connection dies when the first access
            # token expires (~1h), so treat it as a failed connect, not a success.
            logger.warning("Google Calendar OAuth for user %d returned no refresh_token", user_id)
            return _back("error")
        integration_credentials_service.save_google_credentials_json(db, credentials_json)
        log_activity(db, user_id=user_id, action="calendar.connected", entity_type="calendar")
        db.commit()
    except GoogleCalendarError as exc:
        logger.warning("Google Calendar OAuth callback failed for user %d: %s", user_id, exc)
        return _back("error")
    finally:
        db.close()

    return _back("connected")


@router.delete("/google", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def google_disconnect(db: Session = Depends(get_scoped_db)) -> None:
    """
    Forget this user's Google credentials and drop the Google events cached
    for them (source=GOOGLE) -- left behind, they'd keep blocking time in
    the scheduler for a calendar Brain Dump can no longer see. Sessions
    Brain Dump itself created (source=BRAIN_DUMP) are untouched.
    """
    integration_credentials_service.clear_google_credentials(db)
    db.query(CalendarEvent).filter(CalendarEvent.source == EventSource.GOOGLE).delete(
        synchronize_session=False
    )
    log_activity(db, user_id=owner_id(db), action="calendar.disconnected", entity_type="calendar")
    db.commit()


# ---------------------------------------------------------------------------
# Events + sync
# ---------------------------------------------------------------------------


@router.get("/events", response_model=List[CalendarEventRead])
def list_events(
    source: Optional[EventSource] = None, db: Session = Depends(get_scoped_db)
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
def sync_calendar(db: Session = Depends(get_scoped_db)) -> CalendarSyncResponse:
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
    payload: CreateSessionEventRequest, db: Session = Depends(get_scoped_db)
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
