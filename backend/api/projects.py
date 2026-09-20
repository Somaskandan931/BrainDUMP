"""
api/projects.py — CRUD endpoints for Project.

Added in Milestone 3. Not in the original Milestone 1 folder sketch
(which only listed planner/tasks/analytics/calendar), but
Projects need their own CRUD surface since they're the parent entity
for Tasks and the API would be awkward without it — see
ARCHITECTURE.md for the note on this addition.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.ai import episodic_memory, semantic_memory
from backend.api.deps import get_scoped_db
from backend.database import owner_id
from backend.models.project import Project
from backend.models.enums import EpisodicEventType, ProjectStatus, TaskStatus
from backend.schemas.project import ProjectCreate, ProjectUpdate, ProjectRead

router = APIRouter()


@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_scoped_db)) -> Project:
    project = Project(user_id=owner_id(db), **payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/", response_model=List[ProjectRead])
def list_projects(
    status_filter: Optional[ProjectStatus] = None,
    db: Session = Depends(get_scoped_db),
) -> List[Project]:
    query = db.query(Project)
    if status_filter is not None:
        query = query.filter(Project.status == status_filter)
    return query.order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_scoped_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_scoped_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    was_completed = project.status == ProjectStatus.COMPLETED

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    # Episodic Memory (PRD §63): only on the actual active->completed
    # transition, not on every unrelated field edit to an already-
    # completed project (record_event's dedup on (type, date, title)
    # would just update the same row anyway, but the transition check
    # keeps this from running its query on every PUT).
    if project.status == ProjectStatus.COMPLETED and not was_completed:
        total = len(project.tasks)
        completed = sum(1 for t in project.tasks if t.status == TaskStatus.COMPLETED)
        episodic_memory.record_event(
            db,
            EpisodicEventType.PROJECT_COMPLETED,
            title=f"Completed project: {project.name}",
            summary=f'Finished "{project.name}" — {completed}/{total} task(s) completed.',
            occurred_on=datetime.now(timezone.utc).date(),
            payload={"project_id": project.id, "tasks_total": total, "tasks_completed": completed},
        )

        # Semantic Memory (PRD §63): capture this project's task
        # breakdown as a reusable template, then check whether it
        # resembles an earlier completed project closely enough to be
        # a recurring workflow. Same transition guard as episodic
        # memory above, for the same reason.
        semantic_memory.capture_project_template(db, project)
        semantic_memory.detect_recurring_workflow(db, project)

    return project


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(project_id: int, db: Session = Depends(get_scoped_db)) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()

    return {
        "success": True,
        "message": "Project deleted successfully"
    }