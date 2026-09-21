"""
api/v1/activity.py — GET /api/activity/, the account-wide audit feed.

Read-only, cursor-paged (on `id`, stable under concurrent inserts unlike
an offset), and filterable by entity or action. Per-task/project history
lives on the entity's own router instead (GET /api/tasks/{id}/history in
api/v1/tasks.py) since that's the natural place a frontend already goes
to fetch a task.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.v1.deps import get_scoped_db
from backend.app.db.database import owner_id
from backend.app.schemas.activity import ActivityEntryOut, ActivityFeedResponse
from backend.app.services.workspace import activity_service

router = APIRouter()


@router.get("/", response_model=ActivityFeedResponse)
def list_activity(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    cursor: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_scoped_db),
) -> ActivityFeedResponse:
    rows = activity_service.list_activity(
        db,
        user_id=owner_id(db),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        cursor=cursor,
        limit=limit,
    )
    next_cursor = rows[-1].id if len(rows) == limit else None
    return ActivityFeedResponse(items=[ActivityEntryOut.model_validate(r) for r in rows], next_cursor=next_cursor)
