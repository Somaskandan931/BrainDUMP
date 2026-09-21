"""The audit trail end to end: every mutation that's supposed to leave a row does,
GET /api/activity and GET /api/tasks/{id}/history serve it, and nobody can see
anyone else's. Service internals are in tests/unit/test_activity_log.py."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from backend.app.auth import security
from backend.app.db.database import SessionLocal
from backend.app.integrations import google_calendar
from backend.app.jobs.tasks import nightly_replan
from backend.app.models.activity import ActivityLog
from backend.app.models.enums import Importance
from backend.app.services.integrations import integration_credentials_service as creds
from backend.app.services.planning import planner_service, task_parser
from tests.helpers import TEST_PASSWORD, auth_headers, make_task, make_user, scoped_session

_GOOD_CREDENTIALS = json.dumps({"token": "at", "refresh_token": "rt", "client_id": "c", "client_secret": "s"})


@pytest.fixture()
def other_user():
    return make_user("other@example.com", "Other User")


def _rows(user_id=None) -> list[ActivityLog]:
    """Raw rows straight from the table (unscoped), oldest first."""
    with SessionLocal() as everyone:
        query = everyone.query(ActivityLog).order_by(ActivityLog.id)
        if user_id is not None:
            query = query.filter(ActivityLog.user_id == user_id)
        return query.all()


def _actions(user_id=None) -> list[str]:
    return [r.action for r in _rows(user_id)]


def _feed(client, **params) -> dict:
    res = client.get("/api/activity/", params=params)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def test_creating_a_task_is_recorded_with_its_source(client, user):
    task = client.post("/api/tasks/", json={"title": "Write intro"}).json()

    [row] = _rows(user.id)
    assert (row.action, row.entity_type, row.entity_id, row.actor) == ("task.created", "task", task["id"], "user")
    assert row.details == {"title": "Write intro", "project_id": None, "source": "manual"}


def test_editing_a_task_records_old_and_new_values_of_tracked_fields(client, user):
    task = client.post("/api/tasks/", json={"title": "Old", "importance": "low"}).json()

    client.put(f"/api/tasks/{task['id']}", json={"title": "New", "importance": "high"})

    updated = [r for r in _rows(user.id) if r.action == "task.updated"]
    assert len(updated) == 1
    assert updated[0].details["changes"] == {
        "title": {"from": "Old", "to": "New"},
        "importance": {"from": "low", "to": "high"},
    }


def test_a_no_op_edit_records_nothing(client, user):
    task = client.post("/api/tasks/", json={"title": "Same", "importance": "medium"}).json()

    client.put(f"/api/tasks/{task['id']}", json={"title": "Same", "importance": "medium"})

    assert _actions(user.id) == ["task.created"]


def test_editing_free_text_logs_the_field_name_but_not_the_content(client, user):
    task = client.post("/api/tasks/", json={"title": "T"}).json()

    client.put(f"/api/tasks/{task['id']}", json={"description": "my private notes"})

    [row] = [r for r in _rows(user.id) if r.action == "task.updated"]
    assert row.details == {"other_fields": ["description"]}
    assert "private" not in json.dumps(row.details)


def test_a_user_deadline_edit_records_before_and_after_with_utc_offsets(client, user):
    task = client.post("/api/tasks/", json={"title": "T", "deadline": "2026-10-01T09:00:00+00:00"}).json()

    client.put(f"/api/tasks/{task['id']}", json={"deadline": "2026-10-05T09:00:00+00:00"})

    [row] = [r for r in _rows(user.id) if r.action == "task.updated"]
    change = row.details["changes"]["deadline"]
    assert change == {"from": "2026-10-01T09:00:00+00:00", "to": "2026-10-05T09:00:00+00:00"}


def test_complete_skip_and_archive_are_recorded(client, user):
    a = client.post("/api/tasks/", json={"title": "A"}).json()
    b = client.post("/api/tasks/", json={"title": "B"}).json()
    c = client.post("/api/tasks/", json={"title": "C"}).json()

    client.post(f"/api/tasks/{a['id']}/complete")
    client.post(f"/api/tasks/{b['id']}/skip")
    client.delete(f"/api/tasks/{c['id']}")

    by_action = {r.action: r for r in _rows(user.id) if r.action != "task.created"}
    assert by_action["task.completed"].entity_id == a["id"]
    assert by_action["task.completed"].details["title"] == "A"
    assert by_action["task.skipped"].entity_id == b["id"]
    assert by_action["task.archived"].entity_id == c["id"]
    assert by_action["task.archived"].details["from_status"] == "pending"


def test_a_failed_request_leaves_no_row(client, user):
    assert client.put("/api/tasks/9999", json={"title": "x"}).status_code == 404
    assert client.post("/api/tasks/9999/complete").status_code == 404
    assert client.post("/api/tasks/", json={"title": "x", "project_id": 9999}).status_code == 404

    assert _rows(user.id) == []


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def test_project_lifecycle_is_recorded(client, user):
    project = client.post("/api/projects/", json={"name": "Thesis"}).json()
    client.put(f"/api/projects/{project['id']}", json={"name": "Thesis v2"})
    client.put(f"/api/projects/{project['id']}", json={"status": "completed"})

    assert _actions(user.id) == ["project.created", "project.updated", "project.completed"]
    updated = _rows(user.id)[1]
    assert updated.details["changes"]["name"] == {"from": "Thesis", "to": "Thesis v2"}


def test_completing_a_project_writes_one_row_not_two(client, user):
    project = client.post("/api/projects/", json={"name": "P"}).json()

    client.put(f"/api/projects/{project['id']}", json={"status": "completed"})

    assert _actions(user.id).count("project.completed") == 1
    assert "project.updated" not in _actions(user.id)


def test_deleting_a_project_keeps_a_readable_row_after_the_project_is_gone(client, user):
    project = client.post("/api/projects/", json={"name": "Doomed"}).json()
    client.post("/api/tasks/", json={"title": "t1", "project_id": project["id"]})
    client.post("/api/tasks/", json={"title": "t2", "project_id": project["id"]})

    assert client.delete(f"/api/projects/{project['id']}").status_code == 200

    [deleted] = [r for r in _rows(user.id) if r.action == "project.deleted"]
    assert deleted.entity_id == project["id"]
    assert deleted.details == {"name": "Doomed", "task_count": 2}
    # and the trail for the deleted project is still queryable
    assert any(r["action"] == "project.deleted" for r in _feed(client, entity_type="project", entity_id=project["id"])["items"])


# ---------------------------------------------------------------------------
# AI flows
# ---------------------------------------------------------------------------


def test_brain_dump_records_a_summary_and_one_created_row_per_task_without_the_text(client, user, monkeypatch):
    monkeypatch.setattr(
        task_parser,
        "call_model_json",
        lambda *a, **k: {
            "tasks": [
                {"title": "Draft abstract", "project_name": "SourceUp"},
                {"title": "Fix figures", "project_name": "SourceUp"},
            ]
        },
    )
    dump = "SECRET-BRAIN-DUMP-TEXT: draft the abstract and fix the figures"

    res = client.post("/api/planner/brain-dump", json={"text": dump})
    task_ids = sorted(t["id"] for t in res.json()["tasks"])

    rows = _rows(user.id)
    [summary] = [r for r in rows if r.action == "brain_dump.processed"]
    created = [r for r in rows if r.action == "task.created"]
    assert summary.actor == "ai"
    assert sorted(summary.details["task_ids"]) == task_ids
    assert summary.details["characters"] == len(dump)
    assert sorted(r.entity_id for r in created) == task_ids
    assert {r.details["source"] for r in created} == {"brain_dump"}
    assert {r.actor for r in created} == {"ai"}
    assert "SECRET-BRAIN-DUMP-TEXT" not in json.dumps([r.details for r in rows])


def test_a_failed_brain_dump_records_nothing(client, user, monkeypatch):
    monkeypatch.setattr(task_parser, "call_model_json", lambda *a, **k: {"tasks": []})

    assert client.post("/api/planner/brain-dump", json={"text": "hmm"}).status_code == 422

    assert _rows(user.id) == []


def test_goal_plan_records_the_project_and_each_task_as_ai_actions(client, user, monkeypatch):
    monkeypatch.setattr(
        planner_service,
        "call_model_json",
        lambda *a, **k: {
            "project_name": "Interview prep",
            "tasks": [{"title": "DSA", "order": 1}, {"title": "System design", "order": 2}],
        },
    )

    res = client.post("/api/planner/goal", json={"goal_text": "Prepare for interviews in November"})
    assert res.status_code == 200

    rows = _rows(user.id)
    [plan] = [r for r in rows if r.action == "goal.plan_generated"]
    assert (plan.entity_type, plan.actor) == ("project", "ai")
    assert plan.details == {"project_name": "Interview prep", "task_count": 2}
    created = [r for r in rows if r.action == "task.created"]
    assert len(created) == 2 and {r.details["source"] for r in created} == {"goal"}
    assert "November" not in json.dumps([r.details for r in rows])  # goal text stays out


# ---------------------------------------------------------------------------
# Replan: the "why did BrainDUMP move this?" trail
# ---------------------------------------------------------------------------


def _overdue_low_priority_task(db, title="Sinking task"):
    return make_task(db, title, importance=Importance.LOW, deadline_in_days=-1, estimated_hours=2)


def test_replan_records_why_a_deadline_moved_on_that_tasks_history(client, user, db):
    task = _overdue_low_priority_task(db)

    res = client.post("/api/planner/replan")
    assert res.status_code == 200
    assert [t["id"] for t in res.json()["demoted_tasks"]] == [task.id]

    history = client.get(f"/api/tasks/{task.id}/history").json()
    [moved] = [h for h in history if h["action"] == "task.deadline_changed"]
    details = moved["details"]
    assert moved["actor"] == "user"
    assert details["reason"] == "at_risk_demoted"
    assert details["importance"] == "low"
    assert details["was_overdue"] is True
    assert details["push_days"] == 3
    # the recorded before/after are three days apart, both with explicit UTC offsets
    from datetime import datetime

    before, after = datetime.fromisoformat(details["from"]), datetime.fromisoformat(details["to"])
    assert after - before == timedelta(days=3)
    assert before.tzinfo is not None


def test_replan_writes_one_schedule_summary_row_only_when_something_changed(client, user, db):
    client.post("/api/planner/replan")  # empty workspace: nothing to change
    assert "schedule.replanned" not in _actions(user.id)

    task = _overdue_low_priority_task(db)
    client.post("/api/planner/replan")

    [summary] = [r for r in _rows(user.id) if r.action == "schedule.replanned"]
    assert summary.entity_type == "schedule"
    assert summary.details["demoted_task_ids"] == [task.id]


def test_high_importance_at_risk_tasks_are_not_moved_or_logged_as_moved(client, user, db):
    make_task(db, "Critical", importance=Importance.HIGH, deadline_in_days=-1, estimated_hours=2)

    client.post("/api/planner/replan")

    assert "task.deadline_changed" not in _actions(user.id)


def test_nightly_job_attributes_its_changes_to_the_system(client, user, db):
    task = _overdue_low_priority_task(db)

    nightly_replan.run_nightly_job()

    rows = _rows(user.id)
    moved = [r for r in rows if r.action == "task.deadline_changed"]
    assert [r.entity_id for r in moved] == [task.id]
    assert moved[0].actor == "system"
    assert [r.actor for r in rows if r.action == "schedule.replanned"] == ["system"]


def test_nightly_job_purges_old_rows_but_keeps_recent_ones(client, user, monkeypatch):
    from datetime import datetime, timezone

    from backend.app.core import config

    monkeypatch.setattr(config, "ACTIVITY_LOG_RETENTION_DAYS", 30)
    client.post("/api/tasks/", json={"title": "old"})
    client.post("/api/tasks/", json={"title": "recent"})
    old_id = _rows(user.id)[0].id
    with SessionLocal() as everyone:
        everyone.query(ActivityLog).filter(ActivityLog.id == old_id).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(days=90)}
        )
        everyone.commit()

    nightly_replan.run_nightly_job()

    remaining_titles = [r.details.get("title") for r in _rows(user.id) if r.action == "task.created"]
    assert remaining_titles == ["recent"]


# ---------------------------------------------------------------------------
# Schedule + calendar
# ---------------------------------------------------------------------------


def test_start_day_is_recorded_once_even_if_called_again(client, user):
    client.post("/api/schedule/start-day", json={"buffer_multiplier": 1.25})
    client.post("/api/schedule/start-day", json={"buffer_multiplier": 1.5})  # already locked: a no-op

    [row] = [r for r in _rows(user.id) if r.action == "schedule.day_started"]
    assert row.entity_type == "daily_plan"
    assert row.details["buffer_multiplier"] == 1.25


def test_calendar_connect_and_disconnect_are_recorded(anon_client, user, db, monkeypatch):
    from backend.app.core import config

    monkeypatch.setattr(config, "GOOGLE_CALENDAR_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(config, "GOOGLE_CALENDAR_CLIENT_SECRET", "secret")
    monkeypatch.setattr(config, "FRONTEND_URL", "http://frontend.test")
    monkeypatch.setattr(google_calendar, "exchange_code", lambda code: _GOOD_CREDENTIALS)
    state = security.create_state_token(user.id, "google_calendar_oauth")

    res = anon_client.get(
        "/api/calendar/google/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert res.headers["location"].endswith("calendar=connected")

    assert anon_client.delete("/api/calendar/google", headers=auth_headers(user)).status_code == 204
    assert anon_client.delete("/api/calendar/google", headers=auth_headers(user)).status_code == 204  # nothing left to disconnect

    rows = _rows(user.id)
    assert [r.action for r in rows] == ["calendar.connected", "calendar.disconnected"]
    # exact shapes: nothing from the OAuth credentials (tokens, client secret) reaches the trail
    assert rows[0].details == {"provider": "google"}
    assert rows[1].details == {"provider": "google", "cached_events_removed": 0}


# ---------------------------------------------------------------------------
# Auth events (unscoped session: rows name their user explicitly)
# ---------------------------------------------------------------------------


def _capture_emails(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "backend.app.services.email_service.send_email",
        lambda to, subject, body: sent.append((to, subject, body)) or True,
    )
    return sent


def _token_from(body: str) -> str:
    return body.split("token=")[1].split()[0]


def test_registration_verification_and_password_reset_leave_a_secret_free_trail(anon_client, monkeypatch):
    sent = _capture_emails(monkeypatch)
    res = anon_client.post(
        "/api/auth/register", json={"email": "trail@example.com", "password": TEST_PASSWORD, "name": "T"}
    )
    user_id = res.json()["user"]["id"]

    anon_client.post("/api/auth/verify-email/confirm", json={"token": _token_from(sent[0][2])})
    anon_client.post("/api/auth/password-reset/request", json={"email": "trail@example.com"})
    anon_client.post(
        "/api/auth/password-reset/confirm",
        json={"token": _token_from(sent[-1][2]), "new_password": "a-brand-new-password-1"},
    )

    rows = _rows(user_id)
    assert [r.action for r in rows] == ["auth.registered", "auth.email_verified", "auth.password_reset"]
    assert rows[0].details == {"method": "password"}
    blob = json.dumps([r.details for r in rows]) + json.dumps([r.action for r in rows])
    assert TEST_PASSWORD not in blob and "a-brand-new-password-1" not in blob and "token" not in blob.lower()


def test_google_sign_up_is_recorded_once_not_on_every_login(anon_client, monkeypatch):
    from backend.app.api.v1 import auth as auth_api
    from backend.app.auth.google_login import GoogleProfile

    monkeypatch.setattr(
        auth_api, "verify_google_id_token", lambda t: GoogleProfile(sub="g-1", email="g@example.com", name="G", picture=None)
    )

    first = anon_client.post("/api/auth/google", json={"id_token": "t"}).json()
    anon_client.post("/api/auth/google", json={"id_token": "t"})

    rows = _rows(first["user"]["id"])
    assert [(r.action, r.details) for r in rows] == [("auth.registered", {"method": "google"})]


def test_a_rejected_reset_token_records_nothing(anon_client):
    res = anon_client.post(
        "/api/auth/password-reset/confirm", json={"token": "garbage", "new_password": "whatever-password-1"}
    )
    assert res.status_code == 400
    assert _rows() == []


# ---------------------------------------------------------------------------
# GET /api/activity
# ---------------------------------------------------------------------------


def test_feed_is_newest_first_and_shapes_each_item(client, user):
    task = client.post("/api/tasks/", json={"title": "First"}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    feed = _feed(client)

    assert [i["action"] for i in feed["items"]] == ["task.completed", "task.created"]
    assert feed["next_before_id"] is None
    item = feed["items"][0]
    assert set(item) == {"id", "action", "entity_type", "entity_id", "actor", "details", "created_at"}
    assert item["created_at"].endswith("+00:00")  # explicit UTC, like every other Read schema


def test_feed_pages_with_a_cursor(client):
    for i in range(5):
        client.post("/api/tasks/", json={"title": f"t{i}"})

    page1 = _feed(client, limit=2)
    page2 = _feed(client, limit=2, before_id=page1["next_before_id"])
    page3 = _feed(client, limit=2, before_id=page2["next_before_id"])

    titles = [i["details"]["title"] for p in (page1, page2, page3) for i in p["items"]]
    assert titles == ["t4", "t3", "t2", "t1", "t0"]
    assert page3["next_before_id"] is None


def test_feed_filters_by_entity_and_action(client):
    task = client.post("/api/tasks/", json={"title": "T"}).json()
    client.post("/api/projects/", json={"name": "P"})
    client.post(f"/api/tasks/{task['id']}/complete")

    assert {i["entity_type"] for i in _feed(client, entity_type="project")["items"]} == {"project"}
    assert [i["action"] for i in _feed(client, action="task.completed")["items"]] == ["task.completed"]
    assert len(_feed(client, entity_type="task", entity_id=task["id"])["items"]) == 2


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"before_id": 0}, {"entity_id": 0}])
def test_feed_rejects_out_of_range_parameters(client, params):
    assert client.get("/api/activity/", params=params).status_code == 422


def test_there_is_no_way_to_write_or_edit_activity_through_the_api(client, user):
    client.post("/api/tasks/", json={"title": "T"})
    row_id = _rows(user.id)[0].id

    assert client.post("/api/activity/", json={"action": "task.completed"}).status_code == 405
    assert client.put(f"/api/activity/{row_id}", json={"action": "x"}).status_code in (404, 405)
    assert client.delete(f"/api/activity/{row_id}").status_code in (404, 405)


# ---------------------------------------------------------------------------
# GET /api/tasks/{id}/history + tenant isolation
# ---------------------------------------------------------------------------


def test_task_history_tells_the_whole_story_newest_first(client, user):
    task = client.post("/api/tasks/", json={"title": "T", "importance": "low"}).json()
    client.put(f"/api/tasks/{task['id']}", json={"importance": "high"})
    client.post(f"/api/tasks/{task['id']}/skip")
    client.post(f"/api/tasks/{task['id']}/complete")
    other = client.post("/api/tasks/", json={"title": "Unrelated"}).json()

    history = client.get(f"/api/tasks/{task['id']}/history").json()

    assert [h["action"] for h in history] == ["task.completed", "task.skipped", "task.updated", "task.created"]
    assert other["id"] not in {h["entity_id"] for h in history}


def test_task_history_404s_for_a_missing_task(client):
    assert client.get("/api/tasks/9999/history").status_code == 404


def test_task_history_limit_is_validated(client):
    task = client.post("/api/tasks/", json={"title": "T"}).json()
    assert client.get(f"/api/tasks/{task['id']}/history", params={"limit": 0}).status_code == 422
    assert client.get(f"/api/tasks/{task['id']}/history", params={"limit": 1}).status_code == 200


def test_another_users_activity_is_invisible_everywhere(client, user, other_user):
    mine = client.post("/api/tasks/", json={"title": "Mine"}).json()
    theirs = client.post("/api/tasks/", json={"title": "Theirs"}, headers=auth_headers(other_user)).json()

    # their history for their own task works for them...
    assert client.get(f"/api/tasks/{theirs['id']}/history", headers=auth_headers(other_user)).status_code == 200
    # ...but reads as nonexistent to me, exactly like the other task routes
    assert client.get(f"/api/tasks/{theirs['id']}/history").status_code == 404
    # and the feed never mixes tenants, even when asked for their entity directly
    assert {i["details"]["title"] for i in _feed(client)["items"]} == {"Mine"}
    assert _feed(client, entity_type="task", entity_id=theirs["id"])["items"] == []
    assert {i["details"]["title"] for i in client.get("/api/activity/", headers=auth_headers(other_user)).json()["items"]} == {"Theirs"}
    assert mine["id"] != theirs["id"]


def test_activity_rows_are_hidden_from_a_scoped_session_by_the_tenant_listener(user, other_user):
    """The listener registration (not just the endpoint's explicit filter) covers ActivityLog."""
    with SessionLocal() as everyone:
        everyone.add_all(
            [
                ActivityLog(user_id=user.id, action="task.created", actor="user"),
                ActivityLog(user_id=other_user.id, action="task.created", actor="user"),
            ]
        )
        everyone.commit()

    session = scoped_session(user)
    try:
        assert [r.user_id for r in session.query(ActivityLog).all()] == [user.id]
    finally:
        session.close()


def test_deleting_a_user_cascades_their_trail_only(user, other_user):
    with SessionLocal() as everyone:
        everyone.add_all(
            [
                ActivityLog(user_id=user.id, action="task.created", actor="user"),
                ActivityLog(user_id=other_user.id, action="task.created", actor="user"),
            ]
        )
        everyone.commit()

    from sqlalchemy import text

    with SessionLocal() as everyone:
        everyone.execute(text("PRAGMA foreign_keys=ON"))
        everyone.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
        everyone.commit()

    assert [r.user_id for r in _rows()] == [other_user.id]
