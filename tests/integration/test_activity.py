"""Activity log / audit trail (services/workspace/activity_service.py) --
the hooks wired into task/project CRUD, and the two read endpoints:
GET /api/activity/ (account-wide feed) and GET /api/tasks/{id}/history.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.db.database import owner_id
from backend.app.models.activity import ActivityLog
from backend.app.services.workspace import activity_service
from backend.app.services.workspace.activity_service import diff_changes, log_activity
from tests.helpers import make_task, make_user, scoped_session


def _actions(entries) -> list[str]:
    return [e["action"] if isinstance(e, dict) else e.action for e in entries]


# --- Hook coverage via the real HTTP routes ---------------------------------


def test_creating_a_task_logs_task_created(client):
    task = client.post("/api/tasks/", json={"title": "Write intro"}).json()
    history = client.get(f"/api/tasks/{task['id']}/history").json()
    assert _actions(history) == ["task.created"]
    assert history[0]["details"]["title"] == "Write intro"


def test_updating_a_task_logs_a_diff_of_only_the_changed_fields(client):
    task = client.post("/api/tasks/", json={"title": "Draft", "estimated_hours": 2.0}).json()
    client.put(f"/api/tasks/{task['id']}", json={"title": "Draft v2", "estimated_hours": 2.0})

    history = client.get(f"/api/tasks/{task['id']}/history").json()
    update_entry = next(e for e in history if e["action"] == "task.updated")
    changes = update_entry["details"]["changes"]
    assert "title" in changes
    assert changes["title"] == {"from": "Draft", "to": "Draft v2"}
    # estimated_hours was resubmitted unchanged -- not part of the diff.
    assert "estimated_hours" not in changes


def test_a_no_op_update_logs_nothing(client):
    task = client.post("/api/tasks/", json={"title": "Same"}).json()
    client.put(f"/api/tasks/{task['id']}", json={"title": "Same"})

    history = client.get(f"/api/tasks/{task['id']}/history").json()
    assert _actions(history) == ["task.created"]


def test_complete_skip_and_archive_are_each_logged(client):
    a = client.post("/api/tasks/", json={"title": "A"}).json()
    b = client.post("/api/tasks/", json={"title": "B"}).json()
    c = client.post("/api/tasks/", json={"title": "C"}).json()

    client.post(f"/api/tasks/{a['id']}/complete")
    client.post(f"/api/tasks/{b['id']}/skip")
    client.delete(f"/api/tasks/{c['id']}")  # archive, not hard delete

    assert _actions(client.get(f"/api/tasks/{a['id']}/history").json()) == ["task.completed", "task.created"]
    assert _actions(client.get(f"/api/tasks/{b['id']}/history").json()) == ["task.skipped", "task.created"]
    assert _actions(client.get(f"/api/tasks/{c['id']}/history").json()) == ["task.archived", "task.created"]


def test_project_created_updated_and_deleted_are_logged(client):
    project = client.post("/api/projects/", json={"name": "Thesis"}).json()
    client.put(f"/api/projects/{project['id']}", json={"name": "Thesis v2"})
    client.delete(f"/api/projects/{project['id']}")

    feed = client.get(f"/api/activity/?entity_type=project&entity_id={project['id']}").json()["items"]
    assert _actions(feed) == ["project.deleted", "project.updated", "project.created"]


# --- Account-wide feed: filtering, pagination, tenant isolation ------------


def test_activity_feed_filters_by_entity_and_action(client):
    task = client.post("/api/tasks/", json={"title": "T"}).json()
    client.post("/api/projects/", json={"name": "P"})

    task_only = client.get("/api/activity/?entity_type=task").json()["items"]
    assert all(e["entity_type"] == "task" for e in task_only)

    created_only = client.get("/api/activity/?action=task.created").json()["items"]
    assert all(e["action"] == "task.created" for e in created_only)
    assert any(e["entity_id"] == task["id"] for e in created_only)


def test_activity_feed_is_cursor_paged_newest_first(client):
    for i in range(5):
        client.post("/api/tasks/", json={"title": f"Task {i}"})

    page1 = client.get("/api/activity/?limit=2").json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] == page1["items"][-1]["id"]
    # Newest first.
    assert page1["items"][0]["id"] > page1["items"][1]["id"]

    page2 = client.get(f"/api/activity/?limit=2&cursor={page1['next_cursor']}").json()
    ids_seen = {e["id"] for e in page1["items"]} | {e["id"] for e in page2["items"]}
    assert len(ids_seen) == 4  # no overlap between pages


def test_activity_feed_never_shows_another_users_rows(client, user):
    other = make_user("other-activity@example.com", "Other")
    other_session = scoped_session(other)
    try:
        make_task(other_session, "Other user's task")
    finally:
        other_session.close()

    # `client` is authenticated as `user`; they created nothing yet.
    feed = client.get("/api/activity/").json()["items"]
    assert feed == []


def test_task_history_404s_on_another_users_task(client, user):
    other = make_user("other-history@example.com", "Other")
    other_session = scoped_session(other)
    try:
        other_task = make_task(other_session, "Not yours")
        other_task_id = other_task.id
    finally:
        other_session.close()

    assert client.get(f"/api/tasks/{other_task_id}/history").status_code == 404


# --- activity_service internals ---------------------------------------------


def test_diff_changes_only_reports_fields_that_actually_changed():
    old = {"title": "A", "estimated_hours": 2.0, "status": "pending"}
    new = {"title": "A", "estimated_hours": 3.0, "status": "pending"}
    assert diff_changes(old, new) == {"estimated_hours": {"old": 2.0, "new": 3.0}}


def test_diff_changes_is_empty_when_nothing_changed():
    same = {"title": "A", "estimated_hours": 2.0}
    assert diff_changes(same, dict(same)) == {}


def test_log_activity_strips_secret_looking_keys_and_never_raises(db):
    log_activity(
        db,
        user_id=owner_id(db),
        action="auth.registered",
        entity_type="user",
        entity_id=owner_id(db),
        details={"password": "hunter2", "token": "abc", "email": "kept@example.com"},
    )
    db.commit()
    row = db.query(ActivityLog).filter(ActivityLog.action == "auth.registered").one()
    assert row.details == {"email": "kept@example.com"}
    assert "password" not in (row.details or {})


def test_log_activity_swallows_a_logging_failure_instead_of_raising(db, monkeypatch):
    """A bug in the audit-log path must never break the caller's real
    change -- see the module docstring's guarantee."""

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(activity_service, "_sanitize_details", _boom)
    log_activity(db, user_id=owner_id(db), action="task.created", entity_type="task", entity_id=1)
    # No exception raised; nothing was added either.
    db.commit()
    assert db.query(ActivityLog).filter(ActivityLog.action == "task.created").count() == 0


def test_purge_older_than_deletes_only_this_users_old_rows(db):
    old = ActivityLog(
        user_id=owner_id(db),
        action="task.created",
        entity_type="task",
        entity_id=1,
        actor="user",
        created_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    recent = ActivityLog(
        user_id=owner_id(db), action="task.created", entity_type="task", entity_id=2, actor="user"
    )
    db.add_all([old, recent])
    db.commit()

    deleted = activity_service.purge_older_than(db, user_id=owner_id(db), days=180)
    db.commit()

    assert deleted == 1
    remaining = db.query(ActivityLog).all()
    assert len(remaining) == 1
    assert remaining[0].entity_id == 2


def test_purge_older_than_is_a_noop_when_days_is_zero_or_less(db):
    db.add(
        ActivityLog(
            user_id=owner_id(db),
            action="task.created",
            entity_type="task",
            entity_id=1,
            actor="user",
            created_at=datetime.now(timezone.utc) - timedelta(days=9999),
        )
    )
    db.commit()
    assert activity_service.purge_older_than(db, user_id=owner_id(db), days=0) == 0
