"""
schemas/planner.py — Pydantic schemas for the AI planning pipeline endpoints.

Request bodies for brain-dump/goal are simple (one required string field
each) but still go through explicit models rather than a bare `str` query
param, so FastAPI documents them properly in /docs and validates
min_length before an empty string reaches the AI layer.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from backend.schemas.project import ProjectRead
from backend.schemas.task import TaskRead


class BrainDumpRequest(BaseModel):
    text: str = Field(min_length=1)


class BrainDumpResponse(BaseModel):
    projects: List[ProjectRead]
    tasks: List[TaskRead]


class GoalRequest(BaseModel):
    goal_text: str = Field(min_length=1)


class GoalResponse(BaseModel):
    project: ProjectRead
    tasks: List[TaskRead]


class NextTaskResponse(BaseModel):
    """Milestone 5. `task` is null when there's nothing active to work on."""

    task: Optional[TaskRead] = None


class ReplanResponse(BaseModel):
    """Milestone 5. Summary of what deadline_service.replan() changed."""

    rescheduled_count: int
    rescheduled_tasks: List[TaskRead]
    demoted_tasks: List[TaskRead]
    at_risk_tasks: List[TaskRead]
