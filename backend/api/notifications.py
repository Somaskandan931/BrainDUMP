"""
api/notifications.py — Surfaces the Notification System (PRD §27) over HTTP.

Not in the original API Design section's endpoint list, but §44
("Notifications" screen) requires the frontend have something to read —
this is that read side. Computed live on each request (same
"single-user, fits-in-memory, no caching layer needed" reasoning as
analytics_service.py) rather than persisted, since notifications are a
function of current state (schedule, deadlines, clock), not events that
need durable storage.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.notification import NotificationsResponse
from backend.services import notification_service

router = APIRouter()


@router.get("/", response_model=NotificationsResponse)
def list_notifications(db: Session = Depends(get_db)) -> dict:
    return {"notifications": notification_service.generate_notifications(db)}
