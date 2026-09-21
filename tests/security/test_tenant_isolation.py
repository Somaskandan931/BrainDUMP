"""Two users, one database: neither can see, change, or affect the other's data."""

from __future__ import annotations

import json
import pytest

from backend.app.db.database import SessionLocal, owner_id
from backend.app.models.calendar_event import CalendarEvent
from backend.app.models.enums import EventSource, SyncStatus, TaskStatus
from backend.app.models.metrics import ProductivityMetric
from backend.app.models.project import Project
from backend.app.models.settings import Setting
from backend.app.models.task import Task
from backend.app.schemas.user_settings import UserSettingsUpdate
from backend.app.services.planning import schedule_service, scheduler_service
from backend.app.services.workspace import user_settings_service
from tests.helpers import auth_headers, make_project, make_task, make_user, scoped_session, utcnow


@pytest.fixture()
def other_user():
    return make_user("other@example.com", "Other User")


@pytest.fixture()
def other_db(other_user):
    session = scoped_session(other_user)
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_creating_a_row_on_an_unscoped_session_fails_loudly():
    session = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="owner_id"):
            owner_id(session)
    finally:
        session.close()


def test_queries_are_filtered_to_the_sessions_user(db, other_db):
    mine = make_task(db, "Mine")
    theirs = make_task(other_db, "Theirs")

    assert [t.title for t in db.query(Task).all()] == ["Mine"]
    assert [t.title for t in other_db.query(Task).all()] == ["Theirs"]
    assert db.get(Task, theirs.id) is None
    assert other_db.get(Task, mine.id) is None


def test_relationship_lazy_loads_do_not_cross_tenants(db, other_db):
    project = make_project(db, "P")
    make_task(db, "in project", project=project)
    db.expire_all()
    assert [t.title for t in db.get(Project, project.id).tasks] == ["in project"]


def test_bulk_update_and_delete_only_touch_own_rows(db, other_db):
    make_task(db, "mine")
    make_task(other_db, "theirs")

    db.query(Task).delete(synchronize_session=False)
    db.commit()

    assert db.query(Task).count() == 0
    assert other_db.query(Task).count() == 1  # untouched


def test_unscoped_session_sees_everyone(db, other_db):
    make_task(db, "a")
    make_task(other_db, "b")
    with SessionLocal() as everyone:
        assert everyone.query(Task).count() == 2


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

def test_api_lists_only_own_tasks_and_projects(client, db, other_db, other_user):
    make_task(db, "mine")
    make_project(db, "my project")
    make_task(other_db, "theirs")
    make_project(other_db, "their project")

    assert [t["title"] for t in client.get("/api/tasks/").json()] == ["mine"]
    assert [p["name"] for p in client.get("/api/projects/").json()] == ["my project"]

    theirs = {h: client.get(f"/api/{h}/", headers=auth_headers(other_user)).json() for h in ("tasks", "projects")}
    assert [t["title"] for t in theirs["tasks"]] == ["theirs"]
    assert [p["name"] for p in theirs["projects"]] == ["their project"]


def test_api_returns_404_for_another_users_task_on_every_verb(client, other_db):
    foreign = make_task(other_db, "theirs")
    tid = foreign.id

    assert client.get(f"/api/tasks/{tid}").status_code == 404
    assert client.put(f"/api/tasks/{tid}", json={"title": "hijacked"}).status_code == 404
    assert client.post(f"/api/tasks/{tid}/complete").status_code == 404
    assert client.post(f"/api/tasks/{tid}/skip").status_code == 404
    assert client.get(f"/api/tasks/{tid}/subtasks").status_code == 404
    assert client.get(f"/api/tasks/{tid}/explain-estimate").status_code == 404
    assert client.delete(f"/api/tasks/{tid}").status_code == 404

    other_db.expire_all()
    survivor = other_db.get(Task, tid)
    assert survivor is not None and survivor.title == "theirs" and survivor.status == TaskStatus.PENDING


def test_api_cannot_attach_a_task_to_another_users_project(client, db, other_db):
    foreign_project = make_project(other_db, "theirs")
    own_task = make_task(db, "mine")

    create = client.post("/api/tasks/", json={"title": "sneaky", "project_id": foreign_project.id})
    update = client.put(f"/api/tasks/{own_task.id}", json={"project_id": foreign_project.id})

    assert create.status_code == 404 and update.status_code == 404
    assert client.get("/api/tasks/").json()[0]["project_id"] is None
    assert len(client.get("/api/tasks/").json()) == 1  # the rejected create left nothing behind


def test_api_created_rows_belong_to_the_caller(client, user):
    created = client.post("/api/tasks/", json={"title": "via api"})
    assert created.status_code == 201
    with SessionLocal() as everyone:
        assert everyone.get(Task, created.json()["id"]).user_id == user.id


def test_project_delete_does_not_reach_across_tenants(client, other_db):
    foreign = make_project(other_db, "theirs")
    assert client.delete(f"/api/projects/{foreign.id}").status_code == 404
    other_db.expire_all()
    assert other_db.get(Project, foreign.id) is not None


def test_demo_seed_and_reset_are_per_user(client, other_db, other_user):
    assert client.post("/api/demo/seed").status_code == 200
    assert client.post("/api/demo/seed", headers=auth_headers(other_user)).status_code == 200
    assert other_db.query(Project).count() == 3

    client.post("/api/demo/reset")

    other_db.expire_all()
    assert other_db.query(Project).count() == 3  # the other user's demo workspace is untouched
    assert client.get("/api/projects/").json() == []


# ---------------------------------------------------------------------------
# Settings / plans / metrics: same key or date for two users is normal
# ---------------------------------------------------------------------------

def test_settings_are_per_user(db, other_db):
    user_settings_service.update_settings(db, UserSettingsUpdate(weekday_start_hour=6))

    assert user_settings_service.get_settings(db).weekday_start_hour == 6
    assert user_settings_service.get_settings(other_db).weekday_start_hour != 6


def test_two_users_can_start_their_day_on_the_same_date(db, other_db):
    mine = schedule_service.start_day(db, 1.0)
    theirs = schedule_service.start_day(other_db, 1.25)

    assert mine.user_id != theirs.user_id and mine.plan_date == theirs.plan_date
    assert schedule_service.get_today_plan(db).buffer_multiplier == 1.0
    assert schedule_service.get_today_plan(other_db).buffer_multiplier == 1.25


def test_same_google_event_id_for_two_users_does_not_collide(db, other_db):
    """Attendees of one meeting share its Google event id; per-user uniqueness lets both cache it."""
    for session in (db, other_db):
        session.add(
            CalendarEvent(
                user_id=owner_id(session),
                google_event_id="shared-meeting",
                title="Standup",
                start_time=utcnow(),
                end_time=utcnow(),
                source=EventSource.GOOGLE,
                sync_status=SyncStatus.SYNCED,
                synced=True,
            )
        )
        session.commit()

    assert db.query(CalendarEvent).count() == 1
    assert other_db.query(CalendarEvent).count() == 1


# ---------------------------------------------------------------------------
# Scheduling is per user
# ---------------------------------------------------------------------------

def test_scheduler_only_packs_and_blocks_on_the_users_own_tasks_and_events(db, other_db):
    mine = make_task(db, "mine", estimated_hours=1.0)
    make_task(other_db, "theirs", estimated_hours=1.0)

    scheduled = scheduler_service.schedule_pending_tasks(db)

    assert [t.id for t in scheduled] == [mine.id]
    assert db.query(CalendarEvent).count() == 1
    assert other_db.query(CalendarEvent).count() == 0  # nothing was scheduled for them
    assert all(e.user_id == mine.user_id for e in db.query(CalendarEvent).all())


# ---------------------------------------------------------------------------
# Background jobs: one pass per active user, never mixed
# ---------------------------------------------------------------------------

def _rows_by_user(model):
    with SessionLocal() as everyone:
        out: dict = {}
        for row in everyone.query(model).all():
            out.setdefault(row.user_id, []).append(row)
        return out


def test_morning_job_runs_once_per_active_user_and_keeps_data_separate(db, other_db, user, other_user):
    from backend.app.jobs.tasks import morning_plan as morning

    make_task(db, "mine", estimated_hours=1.0)
    make_task(other_db, "theirs", estimated_hours=1.0)

    results = morning.run_morning_job()

    assert set(results) == {user.id, other_user.id}
    assert all("error" not in summary for summary in results.values())
    # Google isn't connected for either of them: skipped, not fatal
    assert all(summary["calendar_sync"]["errors"] for summary in results.values())

    events = _rows_by_user(CalendarEvent)
    assert {uid: len(rows) for uid, rows in events.items()} == {user.id: 1, other_user.id: 1}
    assert {e.title for e in events[user.id]} == {"mine"}
    assert {e.title for e in events[other_user.id]} == {"theirs"}

    summaries = _rows_by_user(Setting)
    for uid in (user.id, other_user.id):
        stored = [s for s in summaries[uid] if s.key == "last_morning_summary"]
        assert len(stored) == 1
        assert json.loads(stored[0].value)["scheduled_count"] == 1


def test_morning_job_skips_inactive_users_and_survives_one_users_failure(db, other_db, user, other_user, monkeypatch):
    from backend.app.models.user import User
    from backend.app.jobs.tasks import morning_plan as morning

    third = make_user("third@example.com")
    with SessionLocal() as s:
        s.get(User, third.id).is_active = False
        s.commit()
    make_task(db, "mine", estimated_hours=1.0)
    make_task(other_db, "theirs", estimated_hours=1.0)

    real = scheduler_service.schedule_pending_tasks

    def flaky(session, *args, **kwargs):
        if session.info["user_id"] == user.id:
            raise RuntimeError("boom")
        return real(session, *args, **kwargs)

    monkeypatch.setattr(scheduler_service, "schedule_pending_tasks", flaky)

    results = morning.run_morning_job()

    assert third.id not in results
    assert results[user.id] == {"error": "boom"}
    assert "error" not in results[other_user.id] and results[other_user.id]["scheduled_count"] == 1


def test_nightly_job_writes_a_metric_row_and_summary_per_user(db, other_db, user, other_user):
    from backend.app.jobs.tasks import nightly_replan as nightly

    make_task(db, "mine", estimated_hours=1.0)

    result = nightly.run_nightly_job()

    assert set(result["users"]) == {user.id, other_user.id}
    assert all("error" not in s for s in result["users"].values())

    metrics = _rows_by_user(ProductivityMetric)
    assert {uid: len(rows) for uid, rows in metrics.items()} == {user.id: 1, other_user.id: 1}
    assert metrics[user.id][0].tasks_planned == 0 and metrics[other_user.id][0].tasks_planned == 0

    summaries = _rows_by_user(Setting)
    for uid in (user.id, other_user.id):
        assert [s.key for s in summaries[uid] if s.key == "last_nightly_summary"] == ["last_nightly_summary"]
    assert "ml_retrain" in result
