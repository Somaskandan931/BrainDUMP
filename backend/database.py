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

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend import config

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


engine = create_engine(
    config.DATABASE_URL,
    echo=config.SQL_ECHO,
    # Needed for SQLite when accessed from multiple threads (FastAPI + APScheduler).
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency: yields a session, guarantees it's closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sync_missing_columns(bind: Engine | None = None) -> None:
    """
    LEGACY PATH -- only runs for a database Alembic doesn't manage yet (see
    init_db()); once a DB has an alembic_version table, schema changes are
    Alembic migrations in backend/migrations/versions instead.

    Before Alembic, `Base.metadata.create_all()` was the only schema tool, and
    it only creates tables that don't exist yet -- it never alters an
    existing table. Every round that's added a column to a model (e.g.
    `recommended_deadline`/`latest_safe_start`/`risk_score`/
    `completion_probability` for the Deadline Engine) has silently
    depended on the person deleting their `data/tasks.db` and starting
    fresh to pick it up. That's a real `no such column` 500 the moment
    someone's existing dev DB predates a newer model field.

    This is a deliberately minimal stand-in for a real migration tool:
    for every table already in Base.metadata, diff its declared columns
    against what SQLite actually has (via `inspect()`), and
    `ALTER TABLE ... ADD COLUMN` for anything missing. SQLite's `ADD
    COLUMN` only supports adding a single column at a time with no
    complex constraints, which is exactly the shape every column added
    to this schema so far has been (nullable, no server-side default) --
    so this covers the real cases without pulling in Alembic for a
    single-user local app. A column that *isn't* nullable and has no
    default is logged and skipped rather than guessed at, since blindly
    backfilling a NOT NULL column's value would be a data decision this
    layer shouldn't make silently.
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

    - Alembic-managed DB (has an alembic_version table): apply any pending
      migrations from backend/migrations/versions.
    - Anything else -- a brand-new file, or a DB created before Alembic was
      introduced: create missing tables, add any columns the models gained
      since (the old stand-in), then stamp it at head so every later schema
      change goes through a migration.

    `bind` defaults to the app's engine; tests pass their own.
    """
    from backend import migrate, models  # noqa: F401  (models registers tables on Base.metadata)

    bind = bind or engine
    if migrate.is_managed(bind):
        migrate.upgrade_to_head(bind)
        return

    Base.metadata.create_all(bind=bind)
    _sync_missing_columns(bind)
    migrate.stamp_head(bind)


if __name__ == "__main__":
    # `python -m backend.database` — quick manual sanity check.
    init_db()
    print(f"Initialized database at {config.DB_PATH}")
