"""
schemas/task.py — Pydantic schemas for Task and Subtask endpoints.

Note what's deliberately absent from *Create/*Update: priority_score,
confidence_score, and context_switch_cost are never client-writable —
those are populated by the AI/ML pipeline in later milestones. The API
only accepts what a human (or a brain-dump parse) can reasonably supply.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import TaskStatus, Importance, EnergyLevel


# --- Subtask -----------------------------------------------------------

class SubtaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    estimated_hours: Optional[float] = Field(default=None, ge=0)


class SubtaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    status: Optional[TaskStatus] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0)
    actual_hours: Optional[float] = Field(default=None, ge=0)


class SubtaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    title: str
    status: TaskStatus
    estimated_hours: Optional[float]
    actual_hours: Optional[float]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# --- Task ----------------------------------------------------------------

class TaskCreate(BaseModel):
    project_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    importance: Importance = Importance.MEDIUM
    energy_requirement: Optional[EnergyLevel] = None
    deadline: Optional[datetime] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0)


class TaskUpdate(BaseModel):
    project_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    importance: Optional[Importance] = None
    energy_requirement: Optional[EnergyLevel] = None
    deadline: Optional[datetime] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0)
    actual_hours: Optional[float] = Field(default=None, ge=0)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: Optional[int]
    title: str
    description: Optional[str]
    status: TaskStatus
    importance: Importance
    energy_requirement: Optional[EnergyLevel]
    deadline: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_hours: Optional[float]
    actual_hours: Optional[float]
    confidence_score: Optional[float]
    priority_score: Optional[float]
    context_switch_cost: Optional[float]
    created_at: datetime
    updated_at: datetime
    subtasks: List[SubtaskRead] = []
