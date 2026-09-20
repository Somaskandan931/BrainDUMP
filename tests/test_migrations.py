"""Alembic setup — backend/migrate.py, backend/migrations/, and database.init_db()."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from backend import migrate, models  # noqa: F401  (registers every table on Base.metadata)
from backend.database import Base, init_db


@pytest.fixture()
def fresh_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    yield engine
    engine.dispose()


def _model_tables() -> set[str]:
    return set(Base.metadata.tables)


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {migrate.VERSION_TABLE}


def test_there_is_exactly_one_head_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(migrate.MIGRATIONS_DIR))
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1
    assert migrate.head_revision() == "0002"


def test_upgrade_on_an_empty_database_creates_every_model_table(fresh_engine):
    migrate.upgrade_to_head(fresh_engine)

    assert _tables(fresh_engine) == _model_tables()
    assert migrate.current_revision(fresh_engine) == migrate.head_revision()


def test_migrations_match_the_models(fresh_engine):
    """The guard that matters: editing a model without writing a migration fails here.
    Fix it with `alembic revision --autogenerate -m "..."`."""
    migrate.upgrade_to_head(fresh_engine)

    with fresh_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True, "render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_then_upgrade_round_trips(fresh_engine):
    migrate.upgrade_to_head(fresh_engine)

    with fresh_engine.begin() as connection:
        command.downgrade(migrate._config(connection), "base")
    assert _tables(fresh_engine) == set()

    migrate.upgrade_to_head(fresh_engine)
    assert _tables(fresh_engine) == _model_tables()


def test_init_db_on_a_new_file_creates_tables_and_stamps_head(fresh_engine):
    init_db(fresh_engine)

    assert _tables(fresh_engine) == _model_tables()
    assert migrate.is_managed(fresh_engine)
    assert migrate.current_revision(fresh_engine) == migrate.head_revision()


def test_init_db_is_idempotent(fresh_engine):
    init_db(fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("INSERT INTO settings (key, value, created_at, updated_at) VALUES ('k', '1', '2026-01-01', '2026-01-01')"))

    init_db(fresh_engine)

    with fresh_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM settings")).scalar() == 1
    assert migrate.current_revision(fresh_engine) == migrate.head_revision()


def test_legacy_database_is_brought_up_to_date_and_stamped(fresh_engine):
    """A tasks.db from before Alembic: tables exist, no alembic_version, and a
    column a later model added is missing. Existing rows must survive."""
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("ALTER TABLE productivity_metrics DROP COLUMN execution_score"))
        connection.execute(
            text(
                "INSERT INTO projects (name, status, created_at, updated_at) "
                "VALUES ('Kept', 'active', '2026-01-01', '2026-01-01')"
            )
        )
    assert not migrate.is_managed(fresh_engine)

    init_db(fresh_engine)

    columns = {c["name"] for c in inspect(fresh_engine).get_columns("productivity_metrics")}
    assert "execution_score" in columns
    assert migrate.current_revision(fresh_engine) == migrate.head_revision()
    with fresh_engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM projects")).scalar() == "Kept"


def test_managed_database_behind_head_is_upgraded_on_boot(fresh_engine):
    """The 'pending migration' path: alembic_version exists but sits at base."""
    migrate.upgrade_to_head(fresh_engine)
    with fresh_engine.begin() as connection:
        command.downgrade(migrate._config(connection), "base")
    assert migrate.is_managed(fresh_engine)
    assert migrate.current_revision(fresh_engine) is None

    init_db(fresh_engine)

    assert _tables(fresh_engine) == _model_tables()
    assert migrate.current_revision(fresh_engine) == migrate.head_revision()


def _make_pre_alembic_db_with_todoist_id(engine) -> None:
    """A tasks.db exactly like one from before Todoist sync was removed: the
    current schema plus tasks.todoist_id and its named unique constraint,
    stamped at the 0001 baseline the way `python -m backend.migrate` did."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)) as ops:
            with ops.batch_alter_table("tasks") as batch_op:
                batch_op.add_column(sa.Column("todoist_id", sa.String(64), nullable=True))
                batch_op.create_unique_constraint("uq_tasks_todoist_id", ["todoist_id"])
        connection.execute(
            text(
                "INSERT INTO tasks (title, status, importance, todoist_id, created_at, updated_at) "
                "VALUES ('Keep me', 'pending', 'medium', 'td-123', '2026-01-01', '2026-01-01'), "
                "       ('Me too', 'completed', 'high', NULL, '2026-01-01', '2026-01-01')"
            )
        )
    with engine.begin() as connection:
        command.stamp(migrate._config(connection), "0001")


def test_legacy_todoist_column_is_dropped_and_rows_survive(fresh_engine):
    """Regression for `alembic check` on a real pre-Alembic tasks.db: drift
    'removed unique constraint uq_tasks_todoist_id' / 'removed column tasks.todoist_id'."""
    _make_pre_alembic_db_with_todoist_id(fresh_engine)
    with fresh_engine.connect() as connection:
        before = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(before, Base.metadata) != []  # the drift is real

    init_db(fresh_engine)

    assert migrate.current_revision(fresh_engine) == migrate.head_revision()
    assert "todoist_id" not in {c["name"] for c in inspect(fresh_engine).get_columns("tasks")}
    with fresh_engine.connect() as connection:
        after = MigrationContext.configure(connection, opts={"compare_type": True, "render_as_batch": True})
        assert compare_metadata(after, Base.metadata) == []
        titles = sorted(r[0] for r in connection.execute(text("SELECT title FROM tasks")))
        assert titles == ["Keep me", "Me too"]


def test_dropping_todoist_id_keeps_the_other_task_columns_and_indexes(fresh_engine):
    _make_pre_alembic_db_with_todoist_id(fresh_engine)
    columns_before = {c["name"] for c in inspect(fresh_engine).get_columns("tasks")} - {"todoist_id"}

    init_db(fresh_engine)

    inspector = inspect(fresh_engine)
    assert {c["name"] for c in inspector.get_columns("tasks")} == columns_before
    assert inspector.get_pk_constraint("tasks")["constrained_columns"] == ["id"]
    assert any(fk["referred_table"] == "projects" for fk in inspector.get_foreign_keys("tasks"))


def test_todoist_cleanup_is_a_no_op_on_a_database_that_never_had_the_column(fresh_engine):
    migrate.upgrade_to_head(fresh_engine)  # 0001 -> 0002 on a schema without the column
    assert migrate.current_revision(fresh_engine) == "0002"
    assert _tables(fresh_engine) == _model_tables()
