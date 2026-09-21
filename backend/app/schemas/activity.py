"""schemas/activity.py — response models for /api/activity and /api/tasks/{id}/history."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ActivityEntryOut(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    actor: str
    details: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityFeedResponse(BaseModel):
    items: list[ActivityEntryOut]
    next_cursor: Optional[int] = None
