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

from backend.ai.ollama_client import OllamaError
from backend.database import get_db
from backend.schemas.planner import (
    BrainDumpRequest,
    BrainDumpResponse,
    GoalRequest,
    GoalResponse,
    NextTaskResponse,
    ReplanResponse,
)
from backend.services.planner_service import (
    PlannerServiceError,
    generate_from_goal,
    get_next_task,
    trigger_replan,
)
from backend.services.task_parser import TaskParserError, parse_brain_dump

router = APIRouter()


@router.post("/brain-dump", response_model=BrainDumpResponse)
def submit_brain_dump(payload: BrainDumpRequest, db: Session = Depends(get_db)) -> BrainDumpResponse:
    """Submit raw brain-dump text -> parsed projects/tasks via the Task Parser agent."""
    try:
        projects, tasks = parse_brain_dump(db, payload.text)
    except TaskParserError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ollama unavailable: {exc}"
        ) from exc
    return BrainDumpResponse(projects=projects, tasks=tasks)


@router.post("/goal", response_model=GoalResponse)
def submit_goal(payload: GoalRequest, db: Session = Depends(get_db)) -> GoalResponse:
    """Submit a high-level goal -> generated project + task roadmap via the Goal Breakdown agent."""
    try:
        project, tasks = generate_from_goal(db, payload.goal_text)
    except PlannerServiceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ollama unavailable: {exc}"
        ) from exc
    return GoalResponse(project=project, tasks=tasks)


@router.get("/next-task", response_model=NextTaskResponse)
def get_next_task_endpoint(db: Session = Depends(get_db)) -> NextTaskResponse:
    """
    The single 'Do Next' task, per ml/priority_model.py's composite
    score. Returns {"task": null} rather than a 404 when nothing's
    active — an empty task list is a normal, valid state (everything's
    done or the user hasn't added anything yet), not an error.
    """
    task = get_next_task(db)
    return NextTaskResponse(task=task)


@router.post("/replan", response_model=ReplanResponse)
def replan_endpoint(db: Session = Depends(get_db)) -> ReplanResponse:
    """
    Trigger dynamic replanning: detect at-risk tasks, demote low/medium
    importance ones that are at risk (buy them runway), then wipe and
    repack the whole future schedule tightest-first by priority. See
    services/deadline_service.py for the full sequence.
    """
    result = trigger_replan(db)
    return ReplanResponse(**result)
