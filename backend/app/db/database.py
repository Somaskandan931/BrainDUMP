"""
database.py — SQLAlchemy engine/session setup.

Provides:
- Base: the declarative base every model in backend/models/ inherits from
- engine: SQLite engine bound to data/tasks.db
- SessionLocal: session factory
- get_db(): FastAPI dependency that yields a session and closes it after use
- init_db(): creates all tables and syncs missing columns — call once on
  app startup

The import of backend.models inside init_db() is deliberately lazy: it
registers every model class on Base.metadata without database.py having
to import models/ at module load time (which would be circular, since
every model imports Base from here).
"""

import logging

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria

from backend.app.core import config

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# The check_same_thread relaxation is SQLite-only (needed since it is
# accessed from multiple threads: FastAPI request threads + the
# APScheduler/worker thread). Postgres has no such flag and does not need
# one -- passing it there would raise, so it is applied conditionally.
engine = create_engine(
    config.DATABASE_URL,
    echo=config.SQL_ECHO,
    connect_args={"check_same_thread": False} if config.IS_SQLITE else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency: yields a session, guarantees it's closed after the request.

    This is the *unscoped* session — no tenant filter applied. Only the
    auth endpoints (before a user is known) and anything that never
    touches a user-owned table should depend on this directly; every
    other route depends on api.deps.get_scoped_db instead, which wraps
    this and turns on row-level tenant isolation for the request — see
    _tenant_filter_listener below.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Multi-user row-level isolation (multi-user auth milestone)
# ---------------------------------------------------------------------------
# Every tenant-owned table (Project, Task, Subtask, Dependency,
# WorkSession, CalendarEvent, Prediction, Setting, DailyPlan,
# EpisodicMemory, SemanticMemory, ProductivityMetric, UsageRecord,
# ActivityLog) carries a
# `user_id` FK. Rather than hand-adding `.filter(Model.user_id ==
# current_user.id)` to every one of the ~40 query sites scattered
# across services/, ai/, ml/, and scheduler/ (and trusting every
# future one to remember it too -- exactly the "a stray unscoped query
# anywhere in that chain leaks data between users silently" risk this
# refactor set out to close), a single SQLAlchemy `do_orm_execute`
# listener applies the filter automatically to every SELECT (and
# ORM-level UPDATE/DELETE) against a tenant-owned model, for the
# lifetime of a Session that has `session.info["user_id"]` set. This is
# SQLAlchemy's documented multi-tenancy recipe (`with_loader_criteria`),
# and it also transparently covers relationship lazy-loads (e.g.
# `project.tasks`), not just top-level queries.
#
# api.deps.get_scoped_db is what actually sets `session.info["user_id"]`
# for a request, from the authenticated user. Background jobs
# (scheduler/morning.py, scheduler/nightly.py) set it by hand, once per
# user, since they have no HTTP request to depend on.
#
# This only covers reads (and updates/deletes against already-scoped
# rows) automatically. A brand-new row's `user_id` still has to be set
# explicitly at creation time -- see owner_id() below, used at every
# `Model(...)` construction site for a tenant-owned table.


def _tenant_models():
    """Lazy import to avoid a circular import (every model imports Base
    from this module) -- same trick init_db() already uses below."""
    from backend.app.models.project import Project
    from backend.app.models.task import Task, Subtask
    from backend.app.models.dependency import Dependency
    from backend.app.models.session import WorkSession
    from backend.app.models.calendar_event import CalendarEvent
    from backend.app.models.prediction import Prediction
    from backend.app.models.settings import Setting
    from backend.app.models.daily_plan import DailyPlan
    from backend.app.models.memory import EpisodicMemory, SemanticMemory
    from backend.app.models.metrics import ProductivityMetric
    from backend.app.models.usage import UsageRecord
    from backend.app.models.activity import ActivityLog

    return (
        Project,
        Task,
        Subtask,
        Dependency,
        WorkSession,
        CalendarEvent,
        Prediction,
        Setting,
        DailyPlan,
        EpisodicMemory,
        SemanticMemory,
        ProductivityMetric,
        UsageRecord,
        ActivityLog,
    )


@event.listens_for(Session, "do_orm_execute")
def _tenant_filter_listener(execute_state) -> None:
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    user_id = execute_state.session.info.get("user_id")
    if user_id is None:
        return
    for model in _tenant_models():
        # Pass a plain boolean expression, NOT a lambda. The callable form of
        # with_loader_criteria goes through SQLAlchemy's lambda-statement cache,
        # which keys on the lambda's code and only re-extracts values from
        # *closure cells*: the original `lambda cls, uid=user_id: ...` (a default
        # argument, not a closure) had the first user's id frozen into the cached
        # statement, so every later session filtered on that user -- every user
        # saw the first user's data. An ordinary expression never enters that
        # cache path, so there is nothing to get wrong; the value is bound as a
        # normal parameter per execution. tests/test_tenant_isolation.py guards it.
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(model, model.user_id == user_id, include_aliases=True)
        )


def owner_id(db: Session) -> int:
    """The current request/job's user id, for stamping onto a newly
    created tenant-owned row (`Task(..., user_id=owner_id(db))`).

    Raises if called on a session that was never scoped -- a missing
    user_id here means a creation path is reachable without
    authentication, which should fail loudly in dev/tests rather than
    silently write an orphaned row.
    """
    user_id = db.info.get("user_id")
    if user_id is None:
        raise RuntimeError(
            "owner_id() called on a database session with no user_id set. "
            "This route/job should depend on api.deps.get_scoped_db (or set "
            "db.info['user_id'] itself for a background job) before creating "
            "a user-owned row."
        )
    return user_id


def _sync_missing_columns(bind: Engine | None = None) -> None:
    """
    LEGACY PATH -- only runs for a database Alembic doesn't manage yet (see
    init_db()); once a DB has an alembic_version table, schema changes are
    Alembic migrations in backend/migrations/versions instead.
    """
    bind = bind or engine
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    with bind.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue  # brand-new table -- create_all() already handled it

            existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue

                if not column.nullable and column.default is None and column.server_default is None:
                    logger.warning(
                        "database: %s.%s is missing but NOT NULL with no default -- "
                        "skipping auto-add; add it manually or reset data/tasks.db",
                        table_name, column.name,
                    )
                    continue

                col_type = column.type.compile(dialect=bind.dialect)
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'))
                logger.info("database: added missing column %s.%s (%s)", table_name, column.name, col_type)


def init_db(bind: Engine | None = None) -> None:
    """
    Bring the database's schema up to date. Safe to call every startup.
    """
    from backend.app.db import migrate
    from backend.app import models  # noqa: F401  (models registers tables on Base.metadata)

    bind = bind or engine
    if migrate.is_managed(bind):
        migrate.upgrade_to_head(bind)
        return

    Base.metadata.create_all(bind=bind)
    _sync_missing_columns(bind)
    migrate.stamp_head(bind)


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {config.DB_PATH}")
