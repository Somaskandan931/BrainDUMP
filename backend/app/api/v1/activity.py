"""
api/activity.py — read-only view of the caller's own audit trail.

There is deliberately no write endpoint: activity rows are only ever
created by the app itself at the moment something happens (see
services/workspace/activity_service.py), so a client can't forge or edit
its own history. Per-task history ("why did this move?") lives at
GET /api/tasks/{id}/history alongside the other task routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.v1.deps import get_scoped_db
from backend.app.schemas.activity import ActivityPage
from backend.app.services.workspace import activity_service

router = APIRouter()


@router.get("/", response_model=ActivityPage)
def list_activity(
    entity_type: Optional[str] = Query(default=None, max_length=32),
    entity_id: Optional[int] = Query(default=None, ge=1),
    action: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=activity_service.DEFAULT_PAGE_SIZE, ge=1, le=activity_service.MAX_PAGE_SIZE),
    before_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_scoped_db),
) -> ActivityPage:
    """The caller's activity, newest first, optionally narrowed to one
    entity (entity_type + entity_id) or one action."""
    rows, next_before_id = activity_service.list_activity(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        limit=limit,
        before_id=before_id,
    )
    return ActivityPage(items=rows, next_before_id=next_before_id)
