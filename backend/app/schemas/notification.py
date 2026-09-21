"""
schemas/notification.py — Pydantic response schema for GET /api/notifications.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class NotificationItem(BaseModel):
    type: str
    severity: str
    message: str
    task_id: Optional[int] = None
    action: Optional[str] = None


class NotificationsResponse(BaseModel):
    notifications: List[NotificationItem]
