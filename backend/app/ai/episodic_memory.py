"""
ai/episodic_memory.py — Episodic Memory tier (PRD §63: "Weekly reviews,
Completed projects, Milestones, Major achievements, Planning decisions").

This was entirely missing -- only ai/memory.py's short-term WorkingMemory
existed. Weekly reviews were computed live and thrown away on every
request, project completions left no trace once the row's status flipped,
and replan() decisions vanished the moment the response was returned.
None of that is "memory" in PRD §63's sense: nothing about what happened
was retained anywhere queryable.

Design:
- Backed by models/memory.py's EpisodicMemory table (durable, unlike
  short-term working memory -- see that module's docstring for why the
  two tiers deliberately live in different places).
- record_event() is idempotent per (event_type, occurred_on, title):
  callers that recompute the same thing repeatedly (weekly_review() runs
  live on every GET, the nightly replan runs every night) must not flood
  the table with duplicate rows for the same real-world event. Milestone
  events pass a natural title (e.g. a specific achievement) so two
  different milestones on the same day don't collide.
- recall_context_text() mirrors ai/memory.py's WorkingMemory.recent_
  context_text() so ai_coach_service can fold episodic recall into the
  same context snapshot alongside short-term memory, satisfying PRD
  §64's "Memory Retrieval" pipeline step for real.
"""

from __future__ import annotations

import json
from datetime import date as date_type
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.database import owner_id
from backend.models.enums import EpisodicEventType
from backend.models.memory import EpisodicMemory


def record_event(
    db: Session,
    event_type: EpisodicEventType,
    title: str,
    summary: str,
    occurred_on: date_type,
    payload: Optional[dict] = None,
) -> EpisodicMemory:
    """
    Insert an episodic event, unless one with the same (event_type,
    occurred_on, title) already exists -- in which case update its
    summary/payload in place instead of creating a duplicate. Commits.
    """
    existing = (
        db.query(EpisodicMemory)
        .filter(
            EpisodicMemory.event_type == event_type,
            EpisodicMemory.occurred_on == occurred_on,
            EpisodicMemory.title == title,
        )
        .first()
    )
    encoded_payload = json.dumps(payload) if payload is not None else None

    if existing is not None:
        existing.summary = summary
        existing.payload = encoded_payload
        db.commit()
        db.refresh(existing)
        return existing

    event = EpisodicMemory(
        user_id=owner_id(db),
        event_type=event_type,
        occurred_on=occurred_on,
        title=title,
        summary=summary,
        payload=encoded_payload,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def recent_events(
    db: Session,
    limit: int = 10,
    event_type: Optional[EpisodicEventType] = None,
) -> List[EpisodicMemory]:
    query = db.query(EpisodicMemory)
    if event_type is not None:
        query = query.filter(EpisodicMemory.event_type == event_type)
    return query.order_by(EpisodicMemory.occurred_on.desc(), EpisodicMemory.id.desc()).limit(limit).all()


def recall_context_text(db: Session, limit: int = 5) -> str:
    """Short plain-text digest of the most recent episodic events, for
    grounding the open-ended LLM fallback prompt in what's already
    happened (a completed project, last week's review) the same way
    working_memory.recent_context_text() grounds it in the current
    conversation."""
    events = recent_events(db, limit=limit)
    if not events:
        return ""
    return "\n".join(f"{e.occurred_on.isoformat()} [{e.event_type.value}]: {e.summary}" for e in events)
