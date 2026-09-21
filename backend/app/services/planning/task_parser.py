"""
services/task_parser.py — Natural language -> structured task/project extraction.

Wraps the Task Parser agent (backend/ai/prompts.py) and the Ollama
transport (backend/ai/ollama_client.py): sends the raw brain-dump text,
parses the returned JSON, resolves each item's project_name against
existing Projects (case-insensitive match, created on first mention),
and writes Task rows. Committed once at the end so a single malformed
item doesn't leave earlier ones half-persisted.

Context resolution beyond simple name-matching (e.g. recognizing that
"Question 3" belongs to an assignment mentioned three brain dumps ago)
needs backend/ai/memory.py's session context, which is a later
milestone -- this pass only resolves what's inside the current text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.db.database import owner_id
from backend.app.services.workspace.activity_service import ACTOR_AI, Action, log_activity
from backend.app.ai.ollama_client import call_model_json
from backend.app.ai.prompts import TASK_PARSER_SYSTEM, build_task_parser_prompt
from backend.app.models.enums import Importance, EnergyLevel
from backend.app.models.project import Project
from backend.app.models.task import Task


class TaskParserError(RuntimeError):
    """Raised when brain-dump text can't be turned into any usable tasks."""


def _resolve_project(
    db: Session,
    name: Optional[str],
    cache: dict[str, Project],
    newly_created: List[Project],
) -> Optional[Project]:
    """
    Get-or-create a Project by name (case-insensitive). `cache` avoids
    re-querying for the same project_name appearing on multiple tasks
    in one brain dump; `newly_created` tracks which ones are new so the
    caller can flush and return them.
    """
    if not name or not name.strip():
        return None

    key = name.strip().lower()
    if key in cache:
        return cache[key]

    project = db.query(Project).filter(Project.name.ilike(name.strip())).first()
    if project is None:
        project = Project(user_id=owner_id(db), name=name.strip())
        db.add(project)
        db.flush()  # assigns project.id without committing the whole transaction yet
        newly_created.append(project)

    cache[key] = project
    return project


def _safe_enum(enum_cls, value, default=None):
    """Fall back to `default` instead of raising if the model returns an unexpected string."""
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _parse_deadline(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_brain_dump(db: Session, text: str) -> Tuple[List[Project], List[Task]]:
    """
    Parse raw brain-dump text into Project/Task rows via the Task Parser
    agent. Returns (created_or_reused_projects, created_tasks). Projects
    that already existed and got a new task attached are included in the
    returned project list too, so the API response reflects the full
    picture -- not just brand-new rows.
    """
    if not text or not text.strip():
        raise TaskParserError("Brain dump text is empty.")

    now_iso = datetime.now(timezone.utc).isoformat()
    prompt = build_task_parser_prompt(text, now_iso)

    # Note: call_model_json can raise OllamaError (Ollama unreachable, or
    # returned invalid JSON) -- deliberately NOT caught here. That's a
    # backend-availability failure, distinct from TaskParserError (the
    # model responded fine but the content wasn't usable), and the two
    # need different HTTP status codes at the API layer (502 vs 422).
    result = call_model_json(prompt, system=TASK_PARSER_SYSTEM, db=db)

    raw_tasks = result.get("tasks") if isinstance(result, dict) else None
    if not raw_tasks:
        raise TaskParserError("The model didn't find any actionable tasks in that brain dump.")

    project_cache: dict[str, Project] = {}
    touched_projects: List[Project] = []
    created_tasks: List[Task] = []

    for item in raw_tasks:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue  # skip malformed entries rather than failing the whole batch

        project = _resolve_project(db, item.get("project_name"), project_cache, touched_projects)
        if project is not None and project not in touched_projects:
            touched_projects.append(project)

        task = Task(
            user_id=owner_id(db),
            project_id=project.id if project is not None else None,
            title=title[:300],
            description=item.get("description") or None,
            importance=_safe_enum(Importance, item.get("importance"), Importance.MEDIUM),
            energy_requirement=_safe_enum(EnergyLevel, item.get("energy_requirement")),
            deadline=_parse_deadline(item.get("deadline")),
            estimated_hours=item.get("estimated_hours"),
        )
        db.add(task)
        created_tasks.append(task)

    if not created_tasks:
        db.rollback()
        raise TaskParserError("The model didn't find any actionable tasks in that brain dump.")

    # Audit trail, staged before the commit so it persists atomically with
    # the rows it describes (flush first: new tasks need ids). One summary
    # row plus one task.created per task, so each task's own history starts
    # with where it came from. The dump text itself is not copied into the
    # log -- only counts and ids.
    db.flush()
    log_activity(
        db,
        Action.BRAIN_DUMP_PROCESSED,
        entity_type="brain_dump",
        actor=ACTOR_AI,
        details={
            "characters": len(text),
            "task_ids": [t.id for t in created_tasks],
            "project_ids": [p.id for p in touched_projects],
        },
    )
    for task in created_tasks:
        log_activity(
            db,
            Action.TASK_CREATED,
            entity_type="task",
            entity_id=task.id,
            actor=ACTOR_AI,
            details={"title": task.title, "project_id": task.project_id, "source": "brain_dump"},
        )

    db.commit()
    for project in touched_projects:
        db.refresh(project)
    for task in created_tasks:
        db.refresh(task)

    return touched_projects, created_tasks
