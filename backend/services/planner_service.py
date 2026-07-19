"""
services/planner_service.py — Orchestrates the end-to-end planning pipeline.

Milestone 4 implemented the "Goal Engine" slice: turning a single
high-level goal into a Project + ordered Task roadmap via the Goal
Breakdown agent (backend/ai/prompts.py).

Milestone 5 adds the rest of the pipeline's back half — Time Estimation,
Priority Calculation, and Schedule Optimization now live in
backend/ml/estimator.py, backend/ml/priority_model.py, and
backend/services/scheduler_service.py, with backend/services/deadline_service.py
handling replanning. get_next_task()/trigger_replan() below are thin
wrappers so api/planner.py has one consistent import surface
(services/planner_service) for the whole pipeline rather than reaching
into scheduler_service/deadline_service directly:

Brain Dump -> Intent Extraction -> Project Detection -> Task Breakdown ->
Time Estimation -> Dependency Detection -> Priority Calculation ->
Schedule Optimization -> Calendar Sync -> Todoist Sync -> Dashboard Update

("Brain Dump -> ... -> Task Breakdown" for the free-text path is
services/task_parser.py; "Task Breakdown" for the single-goal path is
generate_from_goal() below. Dependency Detection and real Calendar/Todoist
Sync are not yet implemented — see backend/ai/AGENTS.md and Milestone 6
respectively.)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.ai.ollama_client import call_model_json
from backend.ai.prompts import TASK_BREAKDOWN_SYSTEM, build_goal_breakdown_prompt
from backend.models.enums import Importance
from backend.models.project import Project
from backend.models.task import Task
from backend.services import deadline_service, scheduler_service


class PlannerServiceError(RuntimeError):
    """Raised when a goal can't be broken down into a usable project/task plan."""


def _safe_importance(value) -> Importance:
    try:
        return Importance(value)
    except (ValueError, TypeError):
        return Importance.MEDIUM


def generate_from_goal(db: Session, goal_text: str) -> Tuple[Project, List[Task]]:
    """
    Turn a single high-level goal into a Project (with goal_text set,
    per models/project.py's Goal Engine convention) plus an ordered
    Task breakdown, via the Goal Breakdown agent. Commits once, after
    validating there's at least one usable task -- a goal that produces
    zero tasks is treated as a parse failure, not an empty project.
    """
    if not goal_text or not goal_text.strip():
        raise PlannerServiceError("Goal text is empty.")

    prompt = build_goal_breakdown_prompt(goal_text)

    # OllamaError (unreachable / invalid JSON) is deliberately not caught
    # here -- see the matching note in services/task_parser.py. It needs
    # to reach the API layer as a distinct case (502) from
    # PlannerServiceError (422: model responded, content was unusable).
    result = call_model_json(prompt, system=TASK_BREAKDOWN_SYSTEM)

    if not isinstance(result, dict):
        raise PlannerServiceError("Model returned an unexpected format for the goal breakdown.")

    raw_tasks = result.get("tasks") or []
    if not raw_tasks:
        raise PlannerServiceError("The model didn't produce a task breakdown for this goal.")

    project_name = (result.get("project_name") or "").strip() or goal_text.strip()[:200]
    project = Project(
        name=project_name[:200],
        description=result.get("project_description") or None,
        goal_text=goal_text.strip(),
    )
    db.add(project)
    db.flush()  # assigns project.id so tasks below can reference it before the final commit

    now = datetime.now(timezone.utc)

    # Sort by the model's suggested "order" field so tasks come back in the
    # sequence the agent intended, even if it didn't emit them in that order.
    def _order_key(item: dict) -> int:
        order = item.get("order")
        return order if isinstance(order, int) else 0

    raw_tasks_sorted = sorted(
        (item for item in raw_tasks if isinstance(item, dict)), key=_order_key
    )

    created_tasks: List[Task] = []
    for item in raw_tasks_sorted:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        offset_days = item.get("deadline_offset_days")
        deadline = (
            now + timedelta(days=offset_days)
            if isinstance(offset_days, (int, float))
            else None
        )

        task = Task(
            project_id=project.id,
            title=title[:300],
            description=item.get("description") or None,
            importance=_safe_importance(item.get("importance")),
            estimated_hours=item.get("estimated_hours"),
            deadline=deadline,
        )
        db.add(task)
        created_tasks.append(task)

    if not created_tasks:
        db.rollback()
        raise PlannerServiceError("The model didn't produce any usable tasks for this goal.")

    db.commit()
    db.refresh(project)
    for task in created_tasks:
        db.refresh(task)

    return project, created_tasks


def get_next_task(db: Session) -> Optional[Task]:
    """
    Milestone 5: thin wrapper around scheduler_service.get_next_task so
    the API layer (api/planner.py) only ever imports from planner_service,
    consistent with how brain-dump/goal above are the only entry points
    into task_parser/this module's own generate_from_goal.
    """
    return scheduler_service.get_next_task(db)


def trigger_replan(db: Session) -> dict:
    """Milestone 5: thin wrapper around deadline_service.replan()."""
    return deadline_service.replan(db)
