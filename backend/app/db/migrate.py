"""
migrate.py — programmatic Alembic entry points.

Used by database.init_db() on every boot and by `python -m backend.migrate`.
Runs Alembic against an *already-open connection* with the script location
resolved from this file, so it works from any working directory and never
needs alembic.ini (that file exists only for the `alembic` CLI:
`alembic revision --autogenerate`, `alembic downgrade`, ...).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

# migrate.py lives at backend/app/db/migrate.py; migrations/ stays at
# backend/migrations (shared infra, not app code), three levels up.
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
VERSION_TABLE = "alembic_version"


def _config(connection: Connection) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False  # don't clobber the app's logging setup
    return cfg


def head_revision() -> str:
    """The newest revision in backend/migrations/versions (there must be exactly one)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(cfg).get_current_head()


def is_managed(engine: Engine) -> bool:
    """True once the database has an alembic_version table, i.e. Alembic owns its schema."""
    return VERSION_TABLE in inspect(engine).get_table_names()


def current_revision(engine: Engine) -> str | None:
    if not is_managed(engine):
        return None
    with engine.connect() as connection:
        from alembic.runtime.migration import MigrationContext

        return MigrationContext.configure(connection).get_current_revision()


def upgrade_to_head(engine: Engine) -> None:
    with engine.begin() as connection:
        command.upgrade(_config(connection), "head")


def stamp_head(engine: Engine) -> None:
    """Record the DB as being at head *without* running any migration -- for a
    database whose tables were just created from the models (or by the
    pre-Alembic init_db()) and therefore already match head."""
    with engine.begin() as connection:
        command.stamp(_config(connection), "head")


if __name__ == "__main__":
    # `python -m backend.migrate` -- bring the real data/tasks.db up to date.
    from backend.app.db.database import engine, init_db

    init_db()
    print(f"{engine.url}: at revision {current_revision(engine)} (head is {head_revision()})")
