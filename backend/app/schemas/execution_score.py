"""
schemas/execution_score.py — Pydantic response schema for
GET /api/analytics/execution-score (PRD §15/§37, Algorithm 8).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import List

from pydantic import BaseModel


class ExecutionScoreComponent(BaseModel):
    name: str
    score: float
    weight: float
    detail: str


class ExecutionScoreResponse(BaseModel):
    score: int
    band: str
    headline: str
    components: List[ExecutionScoreComponent]


class ExecutionScoreTrendPoint(BaseModel):
    date: date_type
    score: int
    band: str


class ExecutionScoreTrendResponse(BaseModel):
    points: List[ExecutionScoreTrendPoint]
