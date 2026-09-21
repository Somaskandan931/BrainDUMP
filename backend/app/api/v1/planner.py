"""
api/planner.py — Endpoints for the AI planning pipeline.

brain-dump and goal are real as of Milestone 4 (Ollama integration and
AI agents): they call into services/task_parser.py and
services/planner_service.py, which talk to the local Ollama model via
backend/ai/ollama_client.py.

next-task and replan are real as of Milestone 5 (scheduler and planning
engine): they call into services/planner_service.py's thin wrappers
around scheduler_service/deadline_service, which are pure Python/SQL —
no Ollama call, no OllamaError handling needed on these two routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.ai.ollama_client import OllamaError
from backend.app.services.ai.usage_service import AIUsageLimitExceeded
from backend.app.api.v1.deps import get_scoped_db
from backend.app.db.database import owner_id
from backend.app.services.workspace.activity_service import log_activity
from backend.app.schemas.planner import (
    BrainDumpRequest,
    BrainDumpResponse,
    DailySummaryResponse,
    GoalRequest,
    GoalResponse,
    NextTaskResponse,
    ReplanResponse,
)
from backend.app.services.planning.planner_service import (
    PlannerServiceError,
    generate_from_goal,
    get_daily_summary,
    get_next_task,
    trigger_replan,
)
from backend.app.services.ai import explanation_service
from backend.app.services.planning.task_parser import TaskParserError, parse_brain_dump

router = APIRouter()


@router.post("/brain-dump", response_model=BrainDumpResponse)
def submit_brain_dump(payload: BrainDumpRequest, db: Session = Depends(get_scoped_db)) -> BrainDumpResponse:
    """Submit raw brain-dump text -> parsed projects/tasks via the Task Parser agent."""
    try:
        projects, tasks = parse_brain_dump(db, payload.text)
    except TaskParserError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except AIUsageLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ollama unavailable: {exc}"
        ) from exc

    # One row per created task (not one row for the whole brain dump) --
    # each task's own history (GET /api/tasks/{id}/history) should show
    # where it came from, and a nightly replan wiping/repacking the
    # schedule later doesn't lose that origin.
    for task in tasks:
        log_activity(
            db, user_id=owner_id(db), action="task.created", entity_type="task", entity_id=task.id,
            actor="ai", details={"title": task.title, "source": "brain_dump"},
        )
    db.commit()
    return BrainDumpResponse(projects=projects, tasks=tasks)


@router.post("/goal", response_model=GoalResponse)
def submit_goal(payload: GoalRequest, db: Session = Depends(get_scoped_db)) -> GoalResponse:
    """Submit a high-level goal -> generated project + task roadmap via the Goal Breakdown agent."""
    try:
        project, tasks = generate_from_goal(db, payload.goal_text)
    except PlannerServiceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except AIUsageLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ollama unavailable: {exc}"
        ) from exc

    log_activity(
        db, user_id=owner_id(db), action="project.created", entity_type="project", entity_id=project.id,
        actor="ai", details={"name": project.name, "source": "goal"},
    )
    for task in tasks:
        log_activity(
            db, user_id=owner_id(db), action="task.created", entity_type="task", entity_id=task.id,
            actor="ai", details={"title": task.title, "source": "goal"},
        )
    db.commit()
    return GoalResponse(project=project, tasks=tasks)


@router.get("/next-task", response_model=NextTaskResponse)
def get_next_task_endpoint(db: Session = Depends(get_scoped_db)) -> NextTaskResponse:
    """
    The single 'Do Next' task, per ml/priority_model.py's composite
    score. Returns {"task": null} rather than a 404 when nothing's
    active — an empty task list is a normal, valid state (everything's
    done or the user hasn't added anything yet), not an error.
    """
    task = get_next_task(db)
    return NextTaskResponse(task=task)


@router.get("/next-task/explain")
def explain_next_task_endpoint(db: Session = Depends(get_scoped_db)) -> dict:
    """
    'Why this task?' — the priority-score breakdown (deadline pressure,
    importance, energy fit, context-switch cost, dependency unlocks)
    behind the current 'Do Next' recommendation. {"explanation": null}
    when there's no active task, same empty-is-valid convention as
    /next-task above.
    """
    return {"explanation": explanation_service.explain_next_task(db)}


@router.get("/today", response_model=DailySummaryResponse)
def get_daily_summary_endpoint(db: Session = Depends(get_scoped_db)) -> DailySummaryResponse:
    """
    The dashboard's Hero Section payload (PRD §37): today's scheduled
    session count, the "do next" task, any at-risk notifications, and a
    one-sentence narration of the plan. Reads scheduler/morning.py's
    cached last run rather than recomputing live -- see
    get_daily_summary()'s docstring. All-default response (nothing
    scheduled, no narration) on a brand-new install that hasn't run the
    morning job yet, not a 404 or 500.
    """
    return DailySummaryResponse(**get_daily_summary(db))


@router.post("/replan", response_model=ReplanResponse)
def replan_endpoint(db: Session = Depends(get_scoped_db)) -> ReplanResponse:
    """
    Trigger dynamic replanning: detect at-risk tasks, demote low/medium
    importance ones that are at risk (buy them runway), then wipe and
    repack the whole future schedule tightest-first by priority. See
    services/deadline_service.py for the full sequence.
    """
    result = trigger_replan(db)
    return ReplanResponse(**result)


@router.get("/replan/explain")
def explain_last_replan_endpoint(db: Session = Depends(get_scoped_db)) -> dict:
    """
    'Why did my schedule change?' — a plain-language narrative for the
    most recent replan (nightly or manual), built from the episodic
    PLANNING_DECISION record and the most recent task that overran its
    estimate. {"explanation": null} if no replan has happened yet.
    """
    return {"explanation": explanation_service.explain_schedule_change(db)}