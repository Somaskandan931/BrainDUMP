"""
api/projects.py — CRUD endpoints for Project.

Added in Milestone 3. Not in the original Milestone 1 folder sketch
(which only listed planner/tasks/analytics/calendar/todoist), but
Projects need their own CRUD surface since they're the parent entity
for Tasks and the API would be awkward without it — see
ARCHITECTURE.md for the note on this addition.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.project import Project
from backend.models.enums import ProjectStatus
from backend.schemas.project import ProjectCreate, ProjectUpdate, ProjectRead

router = APIRouter()


@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/", response_model=List[ProjectRead])
def list_projects(
    status_filter: Optional[ProjectStatus] = None,
    db: Session = Depends(get_db),
) -> List[Project]:
    query = db.query(Project)
    if status_filter is not None:
        query = query.filter(Project.status == status_filter)
    return query.order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)  # cascades to tasks -> subtasks/sessions/etc.
    db.commit()
