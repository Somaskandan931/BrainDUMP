"""
integrations/google_calendar.py — Google Calendar API wrapper.

Milestone 6 implementation:
- OAuth flow + token storage (local only — token.json holds the refresh
  token so the browser consent screen only ever appears once)
- get_free_busy(start, end) -> busy (start, end) intervals for the
  configured calendar
- list_events(start, end) -> full event details, used to populate the
  local CalendarEvent cache with source=GOOGLE rows
- create_event(title, start, end) / update_event(...) / delete_event(...)
  for pushing Brain Dump work sessions (CalendarEvent rows with
  source=BRAIN_DUMP) up to Google

Every public function can raise GoogleCalendarNotConfigured (no
credentials.json yet — a one-time local setup step, not a bug) or the
more general GoogleCalendarError (API call failed). Callers — mainly
services/calendar_sync_service.py — catch these and degrade gracefully
rather than letting a missing OAuth setup take down the scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from backend import config

logger = logging.getLogger(__name__)


class GoogleCalendarError(RuntimeError):
    """Raised when an authenticated call to the Google Calendar API fails."""


class GoogleCalendarNotConfigured(GoogleCalendarError):
    """
    Raised when credentials.json isn't present yet. This is expected on a
    fresh checkout — Google Calendar sync is opt-in and requires a
    one-time OAuth app setup (see INTEGRATIONS.md) — so callers should
    treat it as "feature not turned on", not a crash.
    """


class RemoteEvent(TypedDict):
    google_event_id: str
    title: str
    start: datetime
    end: datetime


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_service: Any = None  # lazily built googleapiclient Resource, cached for the process


def _load_credentials():
    """
    Load cached OAuth credentials from GOOGLE_TOKEN_PATH, refreshing if
    expired, or run the local-server consent flow the first time.
    Imports are local to this function so the whole app doesn't need the
    google-auth-oauthlib import chain unless calendar sync is actually used.
    """
    if not config.GOOGLE_CREDENTIALS_PATH.exists():
        raise GoogleCalendarNotConfigured(
            f"No Google OAuth client secret found at {config.GOOGLE_CREDENTIALS_PATH}. "
            "Download one from Google Cloud Console (APIs & Services -> Credentials -> "
            "Create Credentials -> OAuth client ID -> Desktop app), save it as "
            "credentials.json in the ai_os/ root, then retry. See INTEGRATIONS.md."
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Optional[Credentials] = None
    if config.GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(config.GOOGLE_TOKEN_PATH), config.GOOGLE_CALENDAR_SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.GOOGLE_CREDENTIALS_PATH), config.GOOGLE_CALENDAR_SCOPES
            )
            # Opens a browser tab for one-time consent; blocks until granted.
            # Only ever hit once per machine as long as token.json survives.
            creds = flow.run_local_server(port=0)

        config.GOOGLE_TOKEN_PATH.write_text(creds.to_json())

    return creds


def get_service():
    """Lazily build and cache the Calendar v3 API client for this process."""
    global _service
    if _service is None:
        from googleapiclient.discovery import build

        creds = _load_credentials()
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def reset_service_cache() -> None:
    """Test/utility hook — forces the next get_service() call to rebuild."""
    global _service
    _service = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_event_datetime(node: Dict[str, str]) -> datetime:
    """
    Google returns either {"dateTime": "...", "timeZone": "..."} for timed
    events or {"date": "YYYY-MM-DD"} for all-day events. Normalize both to
    a UTC-aware datetime so downstream code (scheduler_service._as_utc)
    never has to special-case Google's shape.
    """
    if "dateTime" in node:
        return datetime.fromisoformat(node["dateTime"].replace("Z", "+00:00")).astimezone(timezone.utc)
    # All-day event: treat as midnight-to-midnight UTC.
    return datetime.fromisoformat(node["date"]).replace(tzinfo=timezone.utc)


def _run(request, *, action: str):
    from googleapiclient.errors import HttpError

    try:
        return request.execute()
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar API error during {action}: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_events(start: datetime, end: datetime) -> List[RemoteEvent]:
    """
    Full event details (id, title, start, end) for the configured calendar
    in [start, end), skipping cancelled events. Used to populate the local
    CalendarEvent cache (source=GOOGLE) — see calendar_sync_service.
    """
    service = get_service()
    events: List[RemoteEvent] = []
    page_token: Optional[str] = None

    while True:
        request = service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=start.astimezone(timezone.utc).isoformat(),
            timeMax=end.astimezone(timezone.utc).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        )
        result = _run(request, action="list_events")

        for item in result.get("items", []):
            if item.get("status") == "cancelled":
                continue
            if "start" not in item or "end" not in item:
                continue  # malformed/edge-case event, skip rather than crash the sync
            events.append(
                RemoteEvent(
                    google_event_id=item["id"],
                    title=item.get("summary") or "(untitled)",
                    start=_parse_event_datetime(item["start"]),
                    end=_parse_event_datetime(item["end"]),
                )
            )

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return events


def get_free_busy(start: datetime, end: datetime) -> List[tuple]:
    """
    Busy (start, end) intervals only — cheaper than list_events() when the
    caller (scheduler) doesn't need titles, just what's occupied. Uses the
    dedicated freebusy endpoint rather than filtering list_events().
    """
    service = get_service()
    body = {
        "timeMin": start.astimezone(timezone.utc).isoformat(),
        "timeMax": end.astimezone(timezone.utc).isoformat(),
        "items": [{"id": config.GOOGLE_CALENDAR_ID}],
    }
    result = _run(service.freebusy().query(body=body), action="get_free_busy")
    busy = result["calendars"][config.GOOGLE_CALENDAR_ID].get("busy", [])
    return [
        (_parse_event_datetime({"dateTime": b["start"]}), _parse_event_datetime({"dateTime": b["end"]}))
        for b in busy
    ]


def create_event(title: str, start: datetime, end: datetime, description: Optional[str] = None) -> str:
    """Create an event on the configured calendar. Returns the new google_event_id."""
    service = get_service()
    body: Dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start.astimezone(timezone.utc).isoformat()},
        "end": {"dateTime": end.astimezone(timezone.utc).isoformat()},
    }
    if description:
        body["description"] = description

    created = _run(
        service.events().insert(calendarId=config.GOOGLE_CALENDAR_ID, body=body),
        action="create_event",
    )
    return created["id"]


def update_event(
    google_event_id: str,
    *,
    title: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> None:
    """Patch an existing event — only the fields provided are changed."""
    service = get_service()
    body: Dict[str, Any] = {}
    if title is not None:
        body["summary"] = title
    if start is not None:
        body["start"] = {"dateTime": start.astimezone(timezone.utc).isoformat()}
    if end is not None:
        body["end"] = {"dateTime": end.astimezone(timezone.utc).isoformat()}
    if not body:
        return

    _run(
        service.events().patch(calendarId=config.GOOGLE_CALENDAR_ID, eventId=google_event_id, body=body),
        action="update_event",
    )


def delete_event(google_event_id: str) -> None:
    """
    Delete an event. Google returns 404/410 for events already deleted or
    long expired — treated as success (the desired end state already
    holds) rather than surfaced as an error to the caller.
    """
    from googleapiclient.errors import HttpError

    service = get_service()
    try:
        service.events().delete(calendarId=config.GOOGLE_CALENDAR_ID, eventId=google_event_id).execute()
    except HttpError as exc:
        if exc.resp is not None and exc.resp.status in (404, 410):
            return
        raise GoogleCalendarError(f"Google Calendar API error during delete_event: {exc}") from exc
