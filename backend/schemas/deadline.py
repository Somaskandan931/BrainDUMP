"""
schemas/deadline.py — Response shape for the Deadline Engine's buffer plan.

GET /api/tasks/{id}/deadline-plan answers "when should I actually work on
this" at three buffer levels (safe / default / aggressive) instead of just
echoing the raw deadline back. See services/deadline_service.py for the
math; this file only shapes it for the API.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

BufferLevel = Literal["safe", "default", "aggressive"]
BufferStatus = Literal["done", "safe", "tight", "impossible"]


class DeadlineBuffer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: BufferLevel
    target_date: datetime
    days_remaining: float
    free_hours_available: float
    hours_needed: float
    suggested_daily_hours: Optional[float]
    status: BufferStatus
    message: str


class TaskDeadlinePlan(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: int
    title: str
    deadline: datetime
    estimated_hours: Optional[float]
    hours_remaining: float
    buffers: List[DeadlineBuffer]
