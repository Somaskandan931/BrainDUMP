"""
integrations/todoist.py — Todoist API wrapper.

Milestone 6 implementation, built on Todoist's REST API v2 (a personal
API token is enough — no OAuth app registration needed, unlike Google
Calendar). Responsibilities:
- Auth via personal API token (local .env, see config.TODOIST_API_TOKEN)
- push_task(task) -> create a Todoist item from a Brain Dump Task
- pull_tasks() -> list active Todoist items for two-way sync
- close_task() / delete_task() to keep both sides reconciled once a task
  is completed or removed

Every function can raise TodoistNotConfigured (no API token set — a
one-time local setup step) or the more general TodoistError (the HTTP
call itself failed). services/todoist_sync_service.py is the only
caller and treats both the way calendar_sync_service treats Google's
errors: log and continue rather than crash the sync.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

import requests

from backend import config
from backend.models.enums import Importance

logger = logging.getLogger(__name__)


class TodoistError(RuntimeError):
    """Raised when a Todoist API call fails (bad response, network error, etc.)."""


class TodoistNotConfigured(TodoistError):
    """
    Raised when TODOIST_API_TOKEN isn't set. Expected on a fresh
    checkout — Todoist sync is opt-in — so callers treat this as
    "feature not turned on", not a crash.
    """


class RemoteTask(TypedDict):
    todoist_id: str
    content: str
    due: Optional[datetime]
    priority: int  # Todoist scale: 1 (normal) - 4 (urgent)


# Brain Dump's Importance <-> Todoist's 1-4 priority scale. Todoist's "4"
# is its most urgent, so this is intentionally the reverse of a naive
# enum-index mapping.
_IMPORTANCE_TO_TODOIST_PRIORITY = {
    Importance.LOW: 1,
    Importance.MEDIUM: 2,
    Importance.HIGH: 3,
    Importance.CRITICAL: 4,
}
_TODOIST_PRIORITY_TO_IMPORTANCE = {v: k for k, v in _IMPORTANCE_TO_TODOIST_PRIORITY.items()}


def _headers() -> Dict[str, str]:
    if not config.TODOIST_API_TOKEN:
        raise TodoistNotConfigured(
            "TODOIST_API_TOKEN is not set. Generate a personal token at "
            "Todoist -> Settings -> Integrations -> Developer, then add "
            "TODOIST_API_TOKEN=... to ai_os/.env. See INTEGRATIONS.md."
        )
    return {
        "Authorization": f"Bearer {config.TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, *, json: Optional[dict] = None, action: str) -> requests.Response:
    url = f"{config.TODOIST_API_BASE_URL}{path}"
    try:
        response = requests.request(method, url, headers=_headers(), json=json, timeout=10)
    except requests.RequestException as exc:
        raise TodoistError(f"Todoist API request failed during {action}: {exc}") from exc

    if not response.ok:
        raise TodoistError(
            f"Todoist API returned {response.status_code} during {action}: {response.text[:300]}"
        )
    return response


def _parse_due(due_node: Optional[Dict[str, Any]]) -> Optional[datetime]:
    if not due_node:
        return None
    # "datetime" is present for due times; "date" (YYYY-MM-DD) for date-only.
    raw = due_node.get("datetime") or due_node.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Could not parse Todoist due value %r", raw)
        return None


def importance_to_priority(importance: Importance) -> int:
    return _IMPORTANCE_TO_TODOIST_PRIORITY.get(importance, 2)


def priority_to_importance(priority: int) -> Importance:
    return _TODOIST_PRIORITY_TO_IMPORTANCE.get(priority, Importance.MEDIUM)


def pull_tasks() -> List[RemoteTask]:
    """All active (not completed) items from Todoist."""
    response = _request("GET", "/tasks", action="pull_tasks")
    items = response.json()
    return [
        RemoteTask(
            todoist_id=str(item["id"]),
            content=item.get("content", "(untitled)"),
            due=_parse_due(item.get("due")),
            priority=item.get("priority", 1),
        )
        for item in items
    ]


def push_task(
    title: str,
    *,
    due_date: Optional[datetime] = None,
    priority: int = 2,
    description: Optional[str] = None,
) -> RemoteTask:
    """Create a new Todoist item. Returns the created task's id/content/due/priority."""
    body: Dict[str, Any] = {"content": title, "priority": priority}
    if description:
        body["description"] = description
    if due_date is not None:
        # Date-only string is deliberate: Brain Dump deadlines are calendar
        # days ("Assignment due 30 July"), not a specific minute, and
        # Todoist's due_date field expects exactly this YYYY-MM-DD form.
        body["due_date"] = due_date.date().isoformat()

    response = _request("POST", "/tasks", json=body, action="push_task")
    item = response.json()
    return RemoteTask(
        todoist_id=str(item["id"]),
        content=item.get("content", title),
        due=_parse_due(item.get("due")),
        priority=item.get("priority", priority),
    )


def update_task(
    todoist_id: str,
    *,
    title: Optional[str] = None,
    due_date: Optional[datetime] = None,
    priority: Optional[int] = None,
) -> None:
    body: Dict[str, Any] = {}
    if title is not None:
        body["content"] = title
    if due_date is not None:
        body["due_date"] = due_date.date().isoformat()
    if priority is not None:
        body["priority"] = priority
    if not body:
        return
    _request("POST", f"/tasks/{todoist_id}", json=body, action="update_task")


def close_task(todoist_id: str) -> None:
    """
    Mark a Todoist item complete. A 404 here means it's already gone
    (closed/deleted directly in Todoist) — treated as success since the
    desired end state already holds.
    """
    url = f"{config.TODOIST_API_BASE_URL}/tasks/{todoist_id}/close"
    try:
        response = requests.post(url, headers=_headers(), timeout=10)
    except requests.RequestException as exc:
        raise TodoistError(f"Todoist API request failed during close_task: {exc}") from exc
    if response.status_code == 404:
        return
    if not response.ok:
        raise TodoistError(f"Todoist API returned {response.status_code} during close_task: {response.text[:300]}")


def delete_task(todoist_id: str) -> None:
    """Delete a Todoist item outright. 404 treated as already-deleted success."""
    url = f"{config.TODOIST_API_BASE_URL}/tasks/{todoist_id}"
    try:
        response = requests.delete(url, headers=_headers(), timeout=10)
    except requests.RequestException as exc:
        raise TodoistError(f"Todoist API request failed during delete_task: {exc}") from exc
    if response.status_code == 404:
        return
    if not response.ok:
        raise TodoistError(f"Todoist API returned {response.status_code} during delete_task: {response.text[:300]}")
