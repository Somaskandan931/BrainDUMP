"""
Manual Milestone 6 verification script — monkeypatches the Google
Calendar integration module (no real network/credentials available in
this environment) and exercises calendar_sync_service directly against
a throwaway SQLite DB.

Not a pytest suite (Milestone 9 — Testing and Docker — is where this
project gets a real one); run directly with
`python -m tests.manual_milestone6_check` from ai_os/. Safe to keep
around as a quick regression check on the sync logic until then.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.database import Base, SessionLocal, engine
from backend.models.enums import EventSource, Importance, SyncStatus
from backend.models.calendar_event import CalendarEvent
from backend.models.task import Task
from backend.integrations import google_calendar
from backend.services import calendar_sync_service

# Fresh schema each run.
import backend.models  # noqa: F401 registers models
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()
now = datetime.now(timezone.utc)

print("=== Calendar sync ===")

# A task the local scheduler already scheduled (source=BRAIN_DUMP, unsynced).
task = Task(title="Finish CV Assignment Q2", importance=Importance.HIGH)
db.add(task)
db.commit()
db.refresh(task)

pending_event = CalendarEvent(
    task_id=task.id,
    title=task.title,
    start_time=now + timedelta(hours=1),
    end_time=now + timedelta(hours=2),
    source=EventSource.BRAIN_DUMP,
    sync_status=SyncStatus.NOT_SYNCED,
    synced=False,
)
db.add(pending_event)
db.commit()

# A previously-cached Google event that will "disappear" on this pull (deleted remotely).
stale_google_event = CalendarEvent(
    google_event_id="stale-123",
    title="Old College Block",
    start_time=now + timedelta(hours=3),
    end_time=now + timedelta(hours=4),
    source=EventSource.GOOGLE,
    sync_status=SyncStatus.SYNCED,
    synced=True,
)
db.add(stale_google_event)
db.commit()

_create_calls = []


def fake_list_events(start, end):
    return [
        {
            "google_event_id": "gcal-new-1",
            "title": "College",
            "start": now + timedelta(hours=5),
            "end": now + timedelta(hours=6),
        }
    ]


def fake_create_event(title, start, end, description=None):
    _create_calls.append((title, start, end))
    return "gcal-pushed-1"


google_calendar.list_events = fake_list_events
google_calendar.create_event = fake_create_event

pulled, removed = calendar_sync_service.pull_google_events(db, days_ahead=7)
print(f"pull_google_events -> pulled={pulled} removed={removed} (expect pulled=1 removed=1)")

remaining_google = db.query(CalendarEvent).filter(CalendarEvent.source == EventSource.GOOGLE).all()
assert len(remaining_google) == 1 and remaining_google[0].google_event_id == "gcal-new-1", "stale event should be gone, new one present"

pushed, errors = calendar_sync_service.push_pending_sessions(db)
print(f"push_pending_sessions -> pushed={pushed} errors={errors} (expect pushed=1)")
db.refresh(pending_event)
assert pending_event.sync_status == SyncStatus.SYNCED and pending_event.google_event_id == "gcal-pushed-1"
assert _create_calls and _create_calls[0][0] == "Finish CV Assignment Q2"

print("Calendar sync checks passed.\n")
print("ALL MILESTONE 6 CHECKS PASSED")

db.close()
