"""
Manual Milestone 6 verification script — monkeypatches the two
integration modules (no real network/credentials available in this
environment) and exercises calendar_sync_service / todoist_sync_service
directly against a throwaway SQLite DB.

Not a pytest suite (Milestone 9 — Testing and Docker — is where this
project gets a real one); run directly with
`python -m tests.manual_milestone6_check` from ai_os/. Safe to keep
around as a quick regression check on the sync logic until then.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.database import Base, SessionLocal, engine
from backend.models.enums import EventSource, Importance, SyncStatus, TaskStatus
from backend.models.calendar_event import CalendarEvent
from backend.models.task import Task
from backend.integrations import google_calendar, todoist
from backend.services import calendar_sync_service, todoist_sync_service

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

print("=== Todoist sync ===")

# A task already linked to Todoist, still active there.
linked_active = Task(title="Build Report API", importance=Importance.MEDIUM, todoist_id="td-1")
# A task linked to Todoist but that will vanish from the remote list (completed on phone).
linked_vanishing = Task(title="Gym", importance=Importance.LOW, todoist_id="td-2")
# A brand-new local-only task, never pushed.
unlinked = Task(title="Research RAG", importance=Importance.HIGH)
db.add_all([linked_active, linked_vanishing, unlinked])
db.commit()
for t in (linked_active, linked_vanishing, unlinked):
    db.refresh(t)


def fake_pull_tasks():
    return [
        {"todoist_id": "td-1", "content": "Build Report API", "due": None, "priority": 2},
        {"todoist_id": "td-3", "content": "Buy groceries", "due": None, "priority": 1},
        # td-2 intentionally missing -> should trigger local completion
    ]


_push_calls = []
_close_calls = []
_push_counter = {"n": 0}


def fake_push_task(title, due_date=None, priority=2, description=None):
    _push_calls.append(title)
    _push_counter["n"] += 1
    return {"todoist_id": f"td-new-{_push_counter['n']}", "content": title, "due": None, "priority": priority}


def fake_close_task(todoist_id):
    _close_calls.append(todoist_id)


todoist.pull_tasks = fake_pull_tasks
todoist.push_task = fake_push_task
todoist.close_task = fake_close_task

pulled, pull_errors = todoist_sync_service.pull_todoist_tasks(db)
print(f"pull_todoist_tasks -> pulled={pulled} errors={pull_errors} (expect pulled=1)")

db.refresh(linked_vanishing)
assert linked_vanishing.status == TaskStatus.COMPLETED, "vanished-from-Todoist task should be auto-completed"

new_task = db.query(Task).filter(Task.todoist_id == "td-3").first()
assert new_task is not None and new_task.title == "Buy groceries", "new remote task should be imported"

pushed, closed, push_errors = todoist_sync_service.push_pending_tasks(db)
print(f"push_pending_tasks -> pushed={pushed} closed={closed} errors={push_errors} (expect pushed=2, closed=1)")
# pushed=2: `unlinked` ("Research RAG") + the just-imported "Buy groceries" (still todoist_id set though...)

db.refresh(unlinked)
assert unlinked.todoist_id is not None and unlinked.todoist_id.startswith("td-new-"), "unlinked local task should now be linked"
assert "td-2" in _close_calls, "completed, linked task should be closed on Todoist"

print("Todoist sync checks passed.\n")
print("ALL MILESTONE 6 CHECKS PASSED")

db.close()
