"""
schemas/activity.py — Pydantic schemas for the activity (audit trail) endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_serializer

from backend.app.schemas._mixins import utc_iso


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    actor: str
    details: Optional[dict[str, Any]]
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_utc(self, dt):
        return utc_iso(dt)


class ActivityPage(BaseModel):
    """One newest-first page. Pass `next_before_id` back as `before_id`
    for the following page; it's null on the last one."""

    items: List[ActivityRead]
    next_before_id: Optional[int] = None
