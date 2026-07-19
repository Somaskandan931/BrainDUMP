"""
api/tasks.py — CRUD endpoints for Task and Subtask.

Routes stay thin: parse/validate via Pydantic schemas, touch the DB
through the SQLAlchemy session, return an ORM object (FastAPI serializes
it via response_model's from_attributes config). No business logic here
— once backend/services/* exists (Milestone 5), multi-step operations
like "complete task -> log actual_hours -> update Prediction" move there.
For now `complete_task` does the direct, obvious thing.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.task import Task, Subtask
from backend.models.enums import TaskStatus
from backend.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskRead,
    SubtaskCreate,
    SubtaskUpdate,
    SubtaskRead,
)
from backend.services.scheduler_service import complete_task as complete_task_service

router = APIRouter()


# --- Task CRUD ---------------------------------------------------------

@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    task = Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/", response_model=List[TaskRead])
def list_tasks(
    project_id: Optional[int] = None,
    status_filter: Optional[TaskStatus] = None,
    db: Session = Depends(get_db),
) -> List[Task]:
    query = db.query(Task)
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if status_filter is not None:
        query = query.filter(Task.status == status_filter)
    return query.order_by(Task.created_at.desc()).all()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return complete_task_service(db, task)


# --- Subtask CRUD (nested under a task) ---------------------------------

@router.post("/{task_id}/subtasks", response_model=SubtaskRead, status_code=status.HTTP_201_CREATED)
def create_subtask(task_id: int, payload: SubtaskCreate, db: Session = Depends(get_db)) -> Subtask:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    subtask = Subtask(task_id=task_id, **payload.model_dump())
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return subtask


@router.get("/{task_id}/subtasks", response_model=List[SubtaskRead])
def list_subtasks(task_id: int, db: Session = Depends(get_db)) -> List[Subtask]:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.subtasks


@router.put("/subtasks/{subtask_id}", response_model=SubtaskRead)
def update_subtask(subtask_id: int, payload: SubtaskUpdate, db: Session = Depends(get_db)) -> Subtask:
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        raise HTTPException(status_code=404, detail="Subtask not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subtask, field, value)

    db.commit()
    db.refresh(subtask)
    return subtask


@router.delete("/subtasks/{subtask_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subtask(subtask_id: int, db: Session = Depends(get_db)) -> None:
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        raise HTTPException(status_code=404, detail="Subtask not found")
    db.delete(subtask)
    db.commit()
