"""
schemas/workload.py — Response shape for the Workload Engine.

GET /api/analytics/workload answers "how full are my next few days"
(the PRD's Milestone 4 / Milestone 9 heatmap): capacity vs. allocated
hours per day, plus weekly/monthly rollups. See
services/workload_service.py for the math; this file only shapes it.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

WorkloadLevel = Literal["light", "moderate", "full", "overloaded"]


class WorkloadDay(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    weekday: str  # "Mon", "Tue", ... — matches the PRD's heatmap labels
    capacity_hours: float
    allocated_hours: float
    utilization_pct: float  # 0-100+, can exceed 100 if overbooked
    level: WorkloadLevel


class WorkloadPeriod(BaseModel):
    label: str  # "This week" | "This month"
    capacity_hours: float
    allocated_hours: float
    utilization_pct: float
    overload_pct: Optional[float]  # only set once utilization_pct > 100


class WorkloadResponse(BaseModel):
    days: List[WorkloadDay]
    week: WorkloadPeriod
    month: WorkloadPeriod
    peak_day: Optional[str]  # weekday label of the busiest upcoming day
