"""
ai/semantic_memory.py — Semantic Memory tier (PRD §63: "Project
relationships, Dependencies, Recurring workflows, Templates").

The last unbuilt piece of the Memory Architecture. Episodic (what
happened) and Long-Term (how the user works) both existed before this
module; Semantic (how the user's *work* relates to itself — which
projects resemble which, what a project's task breakdown looked like,
what usually depends on what) had no model, no service, and no wiring.

Two relation types, not the PRD's literal four:
- "Templates" -> PROJECT_TEMPLATE: captured at project completion, the
  full task breakdown (titles, importance, estimated_hours) plus that
  project's own intra-project dependency chain (from models/dependency.py).
- "Recurring workflows" + "Project relationships" -> RECURRING_WORKFLOW:
  when a project completes, its task titles are compared against past
  templates; a strong match is recorded as a real relationship between
  the two projects.
- "Dependencies" as its own relation type was deliberately left out.
  Dependency rows (models/dependency.py) are only ever created within
  services/planner_service.py's generate_from_goal(), and every task it
  creates belongs to the *same* new project — there is no code path
  anywhere that creates a Dependency spanning two different projects.
  Building detection for a cross-project dependency relation would be
  dead code for a case the app can't currently produce. If a future
  session adds a way to link tasks across existing projects, this is
  the natural place to add PROJECT_DEPENDENCY alongside these two.

Design mirrors ai/episodic_memory.py: backed by models/memory.py's
SemanticMemory table, record_relation() is idempotent (dedup on
(relation_type, title) — semantic facts aren't date-bound the way
episodic events are, so there's no occurred_on to dedup against),
recall_context_text() mirrors the other tiers' digest for
ai_coach_service's context snapshot.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.database import owner_id
from backend.models.dependency import Dependency
from backend.models.enums import SemanticRelationType
from backend.models.memory import SemanticMemory
from backend.models.project import Project

_RECURRING_WORKFLOW_THRESHOLD = 0.4
_STOPWORDS = {"the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "with"}


def record_relation(
    db: Session,
    relation_type: SemanticRelationType,
    title: str,
    summary: str,
    payload: Optional[dict] = None,
    subject_project_id: Optional[int] = None,
    object_project_id: Optional[int] = None,
) -> SemanticMemory:
    """Insert a semantic relation, unless one with the same
    (relation_type, title) already exists -- in which case update it in
    place instead of creating a duplicate (a re-completed/re-templated
    project shouldn't pile up rows). Commits."""
    existing = (
        db.query(SemanticMemory)
        .filter(
            SemanticMemory.relation_type == relation_type,
            SemanticMemory.title == title,
        )
        .first()
    )
    encoded_payload = json.dumps(payload) if payload is not None else None

    if existing is not None:
        existing.summary = summary
        existing.payload = encoded_payload
        existing.subject_project_id = subject_project_id
        existing.object_project_id = object_project_id
        db.commit()
        db.refresh(existing)
        return existing

    relation = SemanticMemory(
        user_id=owner_id(db),
        relation_type=relation_type,
        title=title,
        summary=summary,
        payload=encoded_payload,
        subject_project_id=subject_project_id,
        object_project_id=object_project_id,
    )
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return relation


def _normalized_title_tokens(titles: List[str]) -> set:
    tokens: set = set()
    for title in titles:
        for word in re.findall(r"[a-z0-9]+", title.lower()):
            if word not in _STOPWORDS:
                tokens.add(word)
    return tokens


def capture_project_template(db: Session, project: Project) -> Optional[SemanticMemory]:
    """Record a completed project's task breakdown as a reusable
    template -- ordered titles, importance, estimated_hours, and the
    project's own intra-project dependency chain. Returns None (and
    records nothing) for a project with no tasks -- there's nothing to
    template."""
    tasks = sorted(project.tasks, key=lambda t: t.id)
    if not tasks:
        return None

    task_ids = {t.id for t in tasks}
    deps = db.query(Dependency).filter(Dependency.task_id.in_(task_ids)).all()
    dep_pairs = [
        {"task_id": d.task_id, "depends_on_task_id": d.depends_on_task_id}
        for d in deps
        if d.depends_on_task_id in task_ids
    ]

    payload = {
        "project_id": project.id,
        "tasks": [
            {
                "title": t.title,
                "importance": t.importance.value if t.importance else None,
                "estimated_hours": t.estimated_hours,
            }
            for t in tasks
        ],
        "dependencies": dep_pairs,
    }

    return record_relation(
        db,
        SemanticRelationType.PROJECT_TEMPLATE,
        title=f"Template: {project.name}",
        summary=f'"{project.name}" — {len(tasks)} task(s), {len(dep_pairs)} dependency link(s).',
        payload=payload,
        subject_project_id=project.id,
    )


def detect_recurring_workflow(db: Session, project: Project) -> Optional[SemanticMemory]:
    """Compare the just-completed project's task titles against past
    PROJECT_TEMPLATE captures (excluding itself); if the token overlap
    (Jaccard similarity over normalized title words) crosses the
    threshold, record a RECURRING_WORKFLOW linking the two projects.
    Returns None if there's no match above threshold, or too little
    signal (no tasks) to compare."""
    tasks = project.tasks
    if not tasks:
        return None

    current_tokens = _normalized_title_tokens([t.title for t in tasks])
    if not current_tokens:
        return None

    past_templates = (
        db.query(SemanticMemory)
        .filter(
            SemanticMemory.relation_type == SemanticRelationType.PROJECT_TEMPLATE,
            SemanticMemory.subject_project_id != project.id,
        )
        .all()
    )

    best_match: Optional[SemanticMemory] = None
    best_score = 0.0
    for template in past_templates:
        if not template.payload:
            continue
        try:
            data = json.loads(template.payload)
        except (TypeError, ValueError):
            continue
        past_titles = [t.get("title", "") for t in data.get("tasks", [])]
        past_tokens = _normalized_title_tokens(past_titles)
        if not past_tokens:
            continue
        overlap = len(current_tokens & past_tokens)
        union = len(current_tokens | past_tokens)
        score = overlap / union if union else 0.0
        if score > best_score:
            best_score = score
            best_match = template

    if best_match is None or best_score < _RECURRING_WORKFLOW_THRESHOLD:
        return None

    matched_project = db.get(Project, best_match.subject_project_id)
    matched_name = matched_project.name if matched_project else "a previous project"

    return record_relation(
        db,
        SemanticRelationType.RECURRING_WORKFLOW,
        title=f"Recurring workflow: {project.name} ~ {matched_name}",
        summary=(
            f'"{project.name}" looks like a repeat of "{matched_name}" '
            f"({round(best_score * 100)}% task-title overlap)."
        ),
        payload={"similarity": round(best_score, 3)},
        subject_project_id=project.id,
        object_project_id=best_match.subject_project_id,
    )


def recent_relations(
    db: Session,
    limit: int = 10,
    relation_type: Optional[SemanticRelationType] = None,
) -> List[SemanticMemory]:
    query = db.query(SemanticMemory)
    if relation_type is not None:
        query = query.filter(SemanticMemory.relation_type == relation_type)
    return query.order_by(SemanticMemory.updated_at.desc(), SemanticMemory.id.desc()).limit(limit).all()


def recall_context_text(db: Session, limit: int = 3) -> str:
    """Short plain-text digest of the most recent semantic relations,
    for the AI coach's context snapshot -- same pattern as
    episodic_memory.recall_context_text()."""
    relations = recent_relations(db, limit=limit, relation_type=SemanticRelationType.RECURRING_WORKFLOW)
    if not relations:
        return ""
    return "; ".join(r.summary for r in relations)
