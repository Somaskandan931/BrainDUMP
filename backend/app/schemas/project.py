"""
schemas/project.py — Pydantic schemas for Project endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    goal_text: Optional[str] = None


class ProjectUpdate(BaseModel):
    """All fields optional — PATCH-style partial update."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    goal_text: Optional[str] = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    status: ProjectStatus
    goal_text: Optional[str]
    created_at: datetime
    updated_at: datetime
