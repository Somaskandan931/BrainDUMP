"""
Alembic environment for BrainDUMP.

- The DB URL comes from backend/config.py (DATABASE_URL) unless the caller
  sets `sqlalchemy.url` on the Alembic Config (the test suite does, to point
  at a throwaway file).
- The app can hand an already-open connection in through
  `config.attributes["connection"]` (backend/database.py does this on boot),
  so migrations run on the same engine the API uses.
- `render_as_batch=True` because SQLite can't ALTER most things in place:
  Alembic's batch mode recreates the table instead.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from backend.app.core import config as app_config
from backend.app import models  # noqa: F401  (registers every model on Base.metadata)
from backend.app.db.database import Base

alembic_config = context.config

if alembic_config.config_file_name is not None and alembic_config.attributes.get("configure_logger", True):
    fileConfig(alembic_config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return alembic_config.get_main_option("sqlalchemy.url") or app_config.DATABASE_URL


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of touching a database (`alembic upgrade head --sql`)."""
    _configure(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = alembic_config.attributes.get("connection")
    if connection is not None:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.begin() as owned_connection:  # begin() commits on exit
            _configure(connection=owned_connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
