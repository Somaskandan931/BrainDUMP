"""
api/demo.py — "Load Demo Workspace" (review Priority 5).

Two endpoints, both mutating, both idempotent-safe to call from a
button: seed synthetic history so the calibration/analytics/execution-
score layers have something to show, and reset to remove it again. See
services/demo_service.py for what's actually created and how it stays
clearly separated from real data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import demo_service

router = APIRouter()


@router.post("/seed")
def seed_demo_workspace(db: Session = Depends(get_db)) -> dict:
    return demo_service.seed_demo_workspace(db)


@router.post("/reset")
def reset_demo_workspace(db: Session = Depends(get_db)) -> dict:
    return demo_service.reset_demo_workspace(db)