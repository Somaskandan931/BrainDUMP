"""services/demo_service.py + /api/demo/* — labeled synthetic history."""

from __future__ import annotations

from datetime import timedelta

from backend.database import owner_id
from backend.models.metrics import ProductivityMetric
from backend.models.project import Project
from backend.models.task import Task
from backend.services.demo_service import DEMO_PREFIX
from tests.helpers import make_project, make_task, utcnow


def test_seed_creates_labeled_projects_tasks_and_history(client, db):
    result = client.post("/api/demo/seed").json()

    assert result["projects_created"] == 3
    assert result["tasks_completed"] > 0 and result["tasks_pending"] == 3
    assert result["already_seeded"] is False

    projects = db.query(Project).all()
    assert projects and all(p.name.startswith(DEMO_PREFIX) for p in projects)
    assert db.query(ProductivityMetric).count() == result["metrics_days"]


def test_seed_twice_does_not_stack_a_duplicate_batch(client, db):
    client.post("/api/demo/seed")
    task_count = db.query(Task).count()

    second = client.post("/api/demo/seed").json()

    assert second["already_seeded"] is True
    assert second["projects_created"] == 0
    assert db.query(Task).count() == task_count


def test_reset_removes_demo_projects_tasks_and_metrics(client, db):
    client.post("/api/demo/seed")
    result = client.post("/api/demo/reset").json()

    assert result["projects_removed"] == 3
    assert result["metrics_removed"] > 0
    assert db.query(Project).count() == 0
    assert db.query(Task).count() == 0
    assert db.query(ProductivityMetric).count() == 0


def test_reset_leaves_real_data_alone(client, db):
    real_project = make_project(db, "My real project")
    real_task = make_task(db, "My real task", project=real_project)
    today = utcnow().date()
    db.add(ProductivityMetric(user_id=owner_id(db), date=today, hours_worked=2.0, tasks_completed=1, tasks_planned=2))
    db.commit()

    client.post("/api/demo/seed")
    client.post("/api/demo/reset")

    db.expire_all()
    assert db.get(Project, real_project.id).name == "My real project"
    assert db.get(Task, real_task.id) is not None
    kept = db.query(ProductivityMetric).one()
    assert kept.date == today and kept.hours_worked == 2.0


def test_seed_never_overwrites_an_existing_real_metric_row(client, db):
    yesterday = utcnow().date() - timedelta(days=1)
    db.add(ProductivityMetric(user_id=owner_id(db), date=yesterday, hours_worked=7.5, tasks_completed=4, tasks_planned=4))
    db.commit()

    client.post("/api/demo/seed")
    client.post("/api/demo/reset")

    db.expire_all()
    survivor = db.query(ProductivityMetric).filter(ProductivityMetric.date == yesterday).one()
    assert survivor.hours_worked == 7.5


def test_reset_with_nothing_seeded_is_a_harmless_no_op(client):
    assert client.post("/api/demo/reset").json() == {"projects_removed": 0, "metrics_removed": 0}


def test_seeded_history_lights_up_calibration_and_streaks(client):
    client.post("/api/demo/seed")

    categories = client.get("/api/analytics/calibration").json()["categories"]
    assert len(categories) >= 2
    biases = {c["category"]: c["bias_pct"] for c in categories}
    assert biases[f"{DEMO_PREFIX} IEEE Paper"] > 20          # deliberately underestimated
    assert biases[f"{DEMO_PREFIX} Admin & Ops"] < 0          # deliberately overestimated

    assert client.get("/api/analytics/streaks").json()["longest_streak_days"] > 0


def test_streaks_are_clean_again_after_reset(client):
    client.post("/api/demo/seed")
    client.post("/api/demo/reset")
    streaks = client.get("/api/analytics/streaks").json()
    assert streaks["longest_streak_days"] == 0
    assert client.get("/api/analytics/calibration").json() == {"categories": []}


def test_every_explain_endpoint_works_on_a_freshly_seeded_workspace(client):
    """The end-to-end path the frontend's 'Load demo workspace' button exercises."""
    client.post("/api/demo/seed")

    explanation = client.get("/api/planner/next-task/explain").json()["explanation"]
    assert explanation and explanation["reasons"]

    task_id = explanation["task_id"]
    assert client.get(f"/api/tasks/{task_id}/explain-estimate").status_code == 200
    assert client.get(f"/api/tasks/{task_id}/explain-deadline-risk").status_code == 200

    assert client.post("/api/planner/replan").status_code == 200
    assert client.get("/api/planner/replan/explain").json()["explanation"]["reasons"]
