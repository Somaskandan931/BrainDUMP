"""
models/memory.py — SQLAlchemy models for EpisodicMemory (PRD §63
"Episodic Memory": weekly reviews, completed projects, milestones,
major achievements, planning decisions) and SemanticMemory (PRD §63
"Semantic Memory": project relationships, dependencies, recurring
workflows, templates).

Unlike ai/memory.py's WorkingMemory (short-term, in-process, gone on
restart), both tiers here are durable: they're the record of things
that actually happened / relationships the system has derived, so they
need real tables. Deliberately one generic table per tier rather than
one table per event/relation type — within a tier, every type shares
the same shape, and a single small table is easier for the matching
ai/*_memory.py module and the AI coach's context snapshot to query
across types than several near-identical tables would be.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import EpisodicEventType, SemanticRelationType, sa_enum
from backend.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.models.project import Project


class EpisodicMemory(Base, TimestampMixin):
    __tablename__ = "episodic_memory"

    id: Mapped[int] = mapped_column(primary_key=True)

    event_type: Mapped[EpisodicEventType] = mapped_column(
        sa_enum(EpisodicEventType), nullable=False
    )

    # The date the event is *about* -- e.g. a weekly review's period_end,
    # a project's completion date -- as opposed to created_at (when the
    # row was written), which is what dedup queries filter on so a
    # re-computed weekly review doesn't create a second row for the same
    # week.
    occurred_on: Mapped[date_type] = mapped_column(Date, nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional JSON-encoded structured detail (e.g. project_id,
    # demoted task ids) -- same "generic text column, caller parses it"
    # pattern as models/settings.py, for the same reason: avoids a
    # migration every time a new event type wants a new field.
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<EpisodicMemory type={self.event_type.value} occurred_on={self.occurred_on}>"


class SemanticMemory(Base, TimestampMixin):
    """PRD §63 "Semantic Memory": project relationships, dependencies,
    recurring workflows, templates.

    Two relation types, not four -- see ai/semantic_memory.py's module
    docstring for why a literal "project-to-project dependency" relation
    type was deliberately left out (nothing in this codebase can create
    a Dependency row that spans two different projects, so detecting one
    would be dead code). PROJECT_TEMPLATE's payload carries the captured
    project's own intra-project dependency chain, which is the real
    "dependencies" data this tier has to offer.

    subject_project_id / object_project_id are both nullable and both
    optional because the two relation types use them differently: a
    PROJECT_TEMPLATE row is *about* one project (subject only) and an
    object_project_id doesn't apply, whereas a RECURRING_WORKFLOW row
    connects two: the project just completed (subject) and the earlier
    project it resembles (object).
    """

    __tablename__ = "semantic_memory"

    id: Mapped[int] = mapped_column(primary_key=True)

    relation_type: Mapped[SemanticRelationType] = mapped_column(
        sa_enum(SemanticRelationType), nullable=False
    )

    subject_project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    object_project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON-encoded structured detail -- for PROJECT_TEMPLATE, the ordered
    # task breakdown (titles, importance, estimated_hours, dependency
    # chain by index); for RECURRING_WORKFLOW, the similarity score and
    # the matched title pairs. Same generic-column rationale as
    # EpisodicMemory.payload above.
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    subject_project: Mapped[Optional["Project"]] = relationship(foreign_keys=[subject_project_id])
    object_project: Mapped[Optional["Project"]] = relationship(foreign_keys=[object_project_id])

    def __repr__(self) -> str:
        return f"<SemanticMemory type={self.relation_type.value} title={self.title!r}>"
