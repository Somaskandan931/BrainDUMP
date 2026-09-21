"""Alembic setup — backend/migrate.py, backend/migrations/, and database.init_db()."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from backend.app.db import migrate
from backend.app import models  # noqa: F401  (registers every table on Base.metadata)
from backend.app.db.database import Base, init_db


@pytest.fixture()
def fresh_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    yield engine
    engine.dispose()


# A minimal valid user row (email/password login) for tests that insert raw SQL
# into tenant-owned tables, which all require a user_id now.
_INSERT_USER = (
    "INSERT INTO users (id, email, hashed_password, is_active, created_at, updated_at) "
    "VALUES (1, 'u@example.com', 'x', 1, '2026-01-01', '2026-01-01')"
)


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
    assert migrate.head_revision() == "0007"


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
        connection.execute(text(_INSERT_USER))
        connection.execute(text("INSERT INTO settings (user_id, key, value, created_at, updated_at) VALUES (1, 'k', '1', '2026-01-01', '2026-01-01')"))

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
        connection.execute(text(_INSERT_USER))
        connection.execute(
            text(
                "INSERT INTO projects (user_id, name, status, created_at, updated_at) "
                "VALUES (1, 'Kept', 'active', '2026-01-01', '2026-01-01')"
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
        connection.execute(text(_INSERT_USER))
        connection.execute(
            text(
                "INSERT INTO tasks (user_id, title, status, importance, todoist_id, created_at, updated_at) "
                "VALUES (1, 'Keep me', 'pending', 'medium', 'td-123', '2026-01-01', '2026-01-01'), "
                "       (1, 'Me too', 'completed', 'high', NULL, '2026-01-01', '2026-01-01')"
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
    migrate.upgrade_to_head(fresh_engine)  # 0001 -> head on a schema that never had the column
    assert migrate.current_revision(fresh_engine) == migrate.head_revision()
    assert _tables(fresh_engine) == _model_tables()


# ---------------------------------------------------------------------------
# The multi-user auth upgrade path (0003 users + user_id, 0004 settings/plans/
# memory/metrics, 0005 per-user google_event_id)
# ---------------------------------------------------------------------------

def _build_pre_auth_database(engine) -> None:
    """A database exactly as it was before multi-user auth: migrated to 0002
    (so no users table, no user_id anywhere) and holding real rows."""
    with engine.begin() as connection:
        command.upgrade(migrate._config(connection), "0002")
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO projects (name, status, created_at, updated_at) VALUES ('Old project', 'active', '2026-01-01', '2026-01-01')")
        )
        connection.execute(
            text(
                "INSERT INTO tasks (project_id, title, status, importance, created_at, updated_at) "
                "VALUES (1, 'Old task', 'pending', 'medium', '2026-01-01', '2026-01-01')"
            )
        )
        connection.execute(
            text("INSERT INTO settings (key, value, created_at, updated_at) VALUES ('k', '1', '2026-01-01', '2026-01-01')")
        )
        connection.execute(
            text("INSERT INTO daily_plans (plan_date, buffer_multiplier, created_at, updated_at) VALUES ('2026-01-01', 1.0, '2026-01-01', '2026-01-01')")
        )
        connection.execute(
            text(
                "INSERT INTO calendar_events (google_event_id, title, start_time, end_time, source, sync_status, synced, created_at, updated_at) "
                "VALUES ('g-1', 'Class', '2026-01-01 09:00', '2026-01-01 10:00', 'google', 'synced', 1, '2026-01-01', '2026-01-01')"
            )
        )


def test_existing_pre_auth_data_survives_the_upgrade_under_the_placeholder_user(fresh_engine):
    """Regression: 0003's placeholder INSERT used to violate ck_users_has_login_method,
    so upgrading any populated pre-auth database failed at boot."""
    _build_pre_auth_database(fresh_engine)

    init_db(fresh_engine)

    assert migrate.current_revision(fresh_engine) == migrate.head_revision()
    with fresh_engine.connect() as connection:
        placeholder = connection.execute(
            text("SELECT id, is_active, hashed_password FROM users WHERE email = 'legacy@local'")
        ).one()
        assert placeholder.is_active == 0  # can never be logged into
        assert placeholder.hashed_password is None
        for table in ("projects", "tasks", "settings", "daily_plans", "calendar_events"):
            owners = {r[0] for r in connection.execute(text(f"SELECT user_id FROM {table}"))}
            assert owners == {placeholder.id}, table
        assert compare_metadata(
            MigrationContext.configure(connection, opts={"compare_type": True, "render_as_batch": True}),
            Base.metadata,
        ) == []


def test_after_the_upgrade_two_users_can_share_a_plan_date_and_a_google_event_id(fresh_engine):
    """The per-user uniqueness the upgrade has to leave behind: the baseline's
    global unique on daily_plans.plan_date and calendar_events.google_event_id
    would make the second user's insert an IntegrityError."""
    _build_pre_auth_database(fresh_engine)
    init_db(fresh_engine)

    with fresh_engine.begin() as connection:
        for uid in (101, 102):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, is_active, created_at, updated_at) "
                    f"VALUES ({uid}, 'u{uid}@example.com', 'x', 1, '2026-01-01', '2026-01-01')"
                )
            )
        for uid in (101, 102):
            connection.execute(
                text(
                    "INSERT INTO daily_plans (user_id, plan_date, buffer_multiplier, created_at, updated_at) "
                    f"VALUES ({uid}, '2026-02-01', 1.0, '2026-01-01', '2026-01-01')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO calendar_events (user_id, google_event_id, title, start_time, end_time, source, sync_status, synced, created_at, updated_at) "
                    f"VALUES ({uid}, 'shared-meeting', 'Standup', '2026-02-01 09:00', '2026-02-01 09:30', 'google', 'synced', 1, '2026-01-01', '2026-01-01')"
                )
            )

    # ...but the same user still can't have two of either
    with pytest.raises(sa.exc.IntegrityError):
        with fresh_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO calendar_events (user_id, google_event_id, title, start_time, end_time, source, sync_status, synced, created_at, updated_at) "
                    "VALUES (101, 'shared-meeting', 'Dup', '2026-02-01 09:00', '2026-02-01 09:30', 'google', 'synced', 1, '2026-01-01', '2026-01-01')"
                )
            )
    with pytest.raises(sa.exc.IntegrityError):
        with fresh_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO daily_plans (user_id, plan_date, buffer_multiplier, created_at, updated_at) "
                    "VALUES (101, '2026-02-01', 1.0, '2026-01-01', '2026-01-01')"
                )
            )
