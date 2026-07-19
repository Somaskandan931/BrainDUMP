"""
schemas/analytics.py — Pydantic response schemas for the four
/api/analytics/* endpoints (Milestone 8, backed by
backend/services/analytics_service.py).

No request schemas here — every route in this group is a parameterless
GET. Kept as a separate module from schemas/task.py etc. because these
are pure read-side aggregates with no matching ORM model to mirror
(ProductivityMetric/Prediction feed them, but the response shapes are
computed rollups, not row passthroughs).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import List, Optional

from pydantic import BaseModel


class ProjectProgress(BaseModel):
    project_id: int
    project_name: str
    tasks_total: int
    tasks_completed: int
    completion_rate: float


class WeeklyReviewResponse(BaseModel):
    period_start: date_type
    period_end: date_type

    tasks_completed: int
    tasks_planned: int
    completion_rate: Optional[float]
    hours_worked: float

    most_productive_day: Optional[str]
    least_productive_day: Optional[str]

    most_underestimated_category: Optional[str]
    most_underestimated_pct: Optional[float]

    missed_deadlines: int
    project_progress: List[ProjectProgress]

    recommendation: str
    ai_generated: bool


class CategoryEstimationError(BaseModel):
    category: str
    sample_count: int
    average_error_pct: float
    bias: str  # "overestimates" | "underestimates" | "accurate"


class EstimationErrorResponse(BaseModel):
    overall_average_error_pct: Optional[float]
    overall_sample_count: int
    by_category: List[CategoryEstimationError]


class StreaksResponse(BaseModel):
    current_streak_days: int
    longest_streak_days: int
    active_today: bool
    last_active_date: Optional[date_type]


class HourBucket(BaseModel):
    hour: int  # 0-23, local-clock hour (see analytics_service for the naive-time caveat)
    hours_logged: float
    sessions_count: int


class ProductivityHoursResponse(BaseModel):
    by_hour: List[HourBucket]
    best_hour: Optional[int]
    lookback_days: int
