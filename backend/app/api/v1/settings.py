"""
api/settings.py — Settings page endpoints: profile, appearance, working
hours, and recurring time blocks. See services/user_settings_service.py
for the storage (existing generic Setting key-value table) and how
get_working_hours()/get_blocked_ranges_for_day() feed the scheduler.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_scoped_db
from backend.schemas.user_settings import (
    TimeBlockCreate,
    TimeBlockRead,
    UserSettingsRead,
    UserSettingsUpdate,
)
from backend.services import user_settings_service

router = APIRouter()


@router.get("", response_model=UserSettingsRead)
def get_settings(db: Session = Depends(get_scoped_db)) -> UserSettingsRead:
    return user_settings_service.get_settings(db)


@router.put("", response_model=UserSettingsRead)
def update_settings(payload: UserSettingsUpdate, db: Session = Depends(get_scoped_db)) -> UserSettingsRead:
    return user_settings_service.update_settings(db, payload)


@router.get("/time-blocks", response_model=List[TimeBlockRead])
def list_time_blocks(db: Session = Depends(get_scoped_db)) -> List[TimeBlockRead]:
    return user_settings_service.list_time_blocks(db)


@router.post("/time-blocks", response_model=TimeBlockRead, status_code=status.HTTP_201_CREATED)
def create_time_block(payload: TimeBlockCreate, db: Session = Depends(get_scoped_db)) -> TimeBlockRead:
    if payload.end_time <= payload.start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_time must be after start_time"
        )
    return user_settings_service.create_time_block(db, payload)


@router.delete("/time-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_time_block(block_id: str, db: Session = Depends(get_scoped_db)) -> None:
    if not user_settings_service.delete_time_block(db, block_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time block not found")