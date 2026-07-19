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
    TaskReorderRequest,
    SubtaskCreate,
    SubtaskUpdate,
    SubtaskRead,
)
from backend.schemas.deadline import TaskDeadlinePlan
from backend.services import deadline_service
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
    # Manually-ordered tasks (drag-to-prioritize in the Today list) come
    # first in the order the user set; anything never dragged falls back
    # to newest-first, same as before sort_order existed.
    return query.order_by(
        Task.sort_order.is_(None), Task.sort_order, Task.created_at.desc()
    ).all()


@router.post("/reorder", response_model=List[TaskRead])
def reorder_tasks(payload: TaskReorderRequest, db: Session = Depends(get_db)) -> List[Task]:
    """
    Persist a drag-to-reorder from the Today list. Assigns sort_order
    0..n-1 in the order given; tasks not included are left untouched (so
    reordering one filtered view doesn't disturb another).
    """
    tasks = db.query(Task).filter(Task.id.in_(payload.task_ids)).all()
    by_id = {t.id: t for t in tasks}
    missing = [tid for tid in payload.task_ids if tid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Task(s) not found: {missing}")

    for index, task_id in enumerate(payload.task_ids):
        by_id[task_id].sort_order = index

    db.commit()
    return [by_id[tid] for tid in payload.task_ids]


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


@router.delete("/{task_id}", response_model=TaskRead)
def archive_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    """
    Soft delete: per PRD §33/§63 ("DELETE /api/tasks/{id} — Archive
    task" / "Soft delete"), this must not hard-delete the row — history,
    predictions, and sessions tied to it (used by analytics and the ML
    trainer) need to survive. Marks the task ARCHIVED instead; archived
    tasks are excluded from the active-task queries the scheduler and
    "Do Next" already filter on.
    """
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = TaskStatus.ARCHIVED
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return complete_task_service(db, task)


@router.get("/{task_id}/deadline-plan", response_model=TaskDeadlinePlan)
def get_deadline_plan(task_id: int, db: Session = Depends(get_db)) -> dict:
    """
    The Deadline Engine: safe / default / aggressive target completion
    dates for this task, each checked against real free calendar time.
    404 if the task doesn't exist, 400 if it has no deadline to plan
    against (there's nothing to compute a buffer from).
    """
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.deadline is None:
        raise HTTPException(status_code=400, detail="Task has no deadline to plan against")
    plan = deadline_service.compute_deadline_plan(db, task)
    deadline_service.persist_deadline_plan(db, task, plan)
    db.commit()
    return plan


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