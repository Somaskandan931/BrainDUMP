"""
schemas/memory.py — Pydantic response schemas for GET /api/memory/*
(PRD §63 AI Memory Architecture — Episodic, Long-Term, and Semantic
tiers).

No request schemas: all three routes are parameterless GETs (episodic
and semantic take an optional query-string filter, not a body) — same
shape as schemas/analytics.py's pure read-side aggregates.
"""

from __future__ import annotations

from datetime import date as date_type, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from backend.app.models.enums import EpisodicEventType, SemanticRelationType


class EpisodicEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EpisodicEventType
    occurred_on: date_type
    title: str
    summary: str


class EpisodicMemoryResponse(BaseModel):
    events: List[EpisodicEventRead]


class EstimationAccuracySummary(BaseModel):
    overall_average_error_pct: Optional[float]
    sample_count: int
    most_biased_category: Optional[str]
    most_biased_direction: Optional[str]  # "overestimates" | "underestimates" | "accurate"


class LongTermProfileResponse(BaseModel):
    generated_at: Optional[datetime]
    preferred_work_hours: List[int]
    estimation_accuracy: EstimationAccuracySummary
    recent_completed_projects: List[str]
    longest_streak_days: int


class SemanticRelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relation_type: SemanticRelationType
    title: str
    summary: str
    subject_project_id: Optional[int]
    object_project_id: Optional[int]


class SemanticMemoryResponse(BaseModel):
    relations: List[SemanticRelationRead]
