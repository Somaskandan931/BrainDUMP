"""schemas/activity.py — response models for /api/activity and /api/tasks/{id}/history."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_serializer

from backend.app.schemas._mixins import utc_iso


class ActivityEntryOut(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    actor: str
    details: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _serialize_created_at(self, dt: datetime) -> Optional[str]:
        return utc_iso(dt)


class ActivityFeedResponse(BaseModel):
    items: list[ActivityEntryOut]
    # Canonical cursor name for the public API.
    next_before_id: Optional[int] = None
    # Backwards-compatible alias retained for existing clients.
    next_cursor: Optional[int] = None
