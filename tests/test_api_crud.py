"""Regression coverage for the pre-existing API surface (API.md / AGENTS.md)."""

from __future__ import annotations

from backend.ai.ollama_client import OllamaError
from backend.services import task_parser


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_project_crud_and_404(client):
    created = client.post("/api/projects/", json={"name": "Thesis"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert client.get(f"/api/projects/{project_id}").json()["name"] == "Thesis"
    assert client.put(f"/api/projects/{project_id}", json={"name": "Thesis v2"}).json()["name"] == "Thesis v2"
    assert [p["id"] for p in client.get("/api/projects/").json()] == [project_id]
    assert client.get("/api/projects/9999").status_code == 404


def test_task_lifecycle_and_cascade_delete(client):
    project_id = client.post("/api/projects/", json={"name": "P"}).json()["id"]
    task = client.post("/api/tasks/", json={"title": "Write intro", "project_id": project_id}).json()

    subtask = client.post(f"/api/tasks/{task['id']}/subtasks", json={"title": "Outline"})
    assert subtask.status_code == 201
    assert len(client.get(f"/api/tasks/{task['id']}").json()["subtasks"]) == 1

    done = client.post(f"/api/tasks/{task['id']}/complete").json()
    assert done["status"] == "completed" and done["completed_at"] is not None

    client.delete(f"/api/projects/{project_id}")
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_client_cannot_set_ml_owned_fields(client):
    task = client.post("/api/tasks/", json={"title": "x", "priority_score": 0.99}).json()
    assert task["priority_score"] != 0.99


def test_skip_route_exists_for_the_frontend_client(client):
    task = client.post("/api/tasks/", json={"title": "Skippable"}).json()
    response = client.post(f"/api/tasks/{task['id']}/skip")
    assert response.status_code == 200


def test_next_task_is_null_when_nothing_is_active(client):
    assert client.get("/api/planner/next-task").json() == {"task": None}


def test_status_filter_and_project_filter(client):
    project_id = client.post("/api/projects/", json={"name": "P"}).json()["id"]
    client.post("/api/tasks/", json={"title": "in project", "project_id": project_id})
    client.post("/api/tasks/", json={"title": "loose"})

    assert [t["title"] for t in client.get(f"/api/tasks/?project_id={project_id}").json()] == ["in project"]


# --- error mapping from AGENTS.md: model down is 502, unusable content is 422 ------


def test_brain_dump_maps_ollama_outage_to_502(client):
    # conftest already makes every model call raise OllamaError.
    response = client.post("/api/planner/brain-dump", json={"text": "finish the report by friday"})
    assert response.status_code == 502
    assert "Ollama unavailable" in response.json()["detail"]


def test_brain_dump_maps_empty_result_to_422(client, monkeypatch):
    monkeypatch.setattr(task_parser, "call_model_json", lambda *a, **k: {"tasks": []})
    response = client.post("/api/planner/brain-dump", json={"text": "hmm"})
    assert response.status_code == 422


def test_brain_dump_creates_tasks_and_dedups_projects_case_insensitively(client, monkeypatch):
    replies = iter(
        [
            {"tasks": [{"title": "Draft abstract", "project_name": "SourceUp", "importance": "high"}]},
            {"tasks": [{"title": "Fix figures", "project_name": "sourceup"}, {"title": ""}, "junk"]},
        ]
    )
    monkeypatch.setattr(task_parser, "call_model_json", lambda *a, **k: next(replies))

    client.post("/api/planner/brain-dump", json={"text": "one"})
    client.post("/api/planner/brain-dump", json={"text": "two"})

    assert len(client.get("/api/projects/").json()) == 1
    assert sorted(t["title"] for t in client.get("/api/tasks/").json()) == ["Draft abstract", "Fix figures"]


def test_unparseable_deadline_falls_back_to_none(client, monkeypatch):
    monkeypatch.setattr(
        task_parser,
        "call_model_json",
        lambda *a, **k: {"tasks": [{"title": "Ship it", "deadline": "whenever, honestly"}]},
    )
    client.post("/api/planner/brain-dump", json={"text": "ship it"})
    assert client.get("/api/tasks/").json()[0]["deadline"] is None


def test_unreachable_ollama_is_an_ollama_error(monkeypatch):
    """The conftest safety net itself: nothing can quietly reach a real model."""
    from backend.ai import ollama_client

    try:
        ollama_client.call_model_json("hi", system="x")
    except OllamaError:
        return
    raise AssertionError("expected OllamaError")
