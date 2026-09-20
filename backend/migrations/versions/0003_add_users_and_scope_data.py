"""add users and scope existing data to a user

The first wave of the multi-user migration. Creates the `users` table,
then adds a `user_id` FK to every table that previously had no owner:
projects, tasks, subtasks, dependencies, work_sessions, calendar_events,
predictions.

Every existing row in this database was created before multi-user auth
existed, so there's no real owner to assign them to -- they're all
backfilled to a single placeholder account (legacy@local) instead of
being dropped, so nobody's existing data disappears on upgrade. That
account has no usable password or Google identity; it exists purely as
a migration anchor, not something anyone is meant to log into. (0004,
the second wave, backfills the remaining user-level tables --
settings/daily_plans/memory/metrics -- to this same placeholder id.)

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLACEHOLDER_EMAIL = "legacy@local"
# ck_users_has_login_method requires a password hash or a google_sub, so the
# anchor account needs one of them to be insertable at all. A real Google
# "sub" is a numeric string, so this value can never match one -- the account
# still can't be logged into (and is_active=0 on top of that).
_PLACEHOLDER_GOOGLE_SUB = "legacy-placeholder-not-a-real-google-account"

# table_name -> nullable (subtasks/tasks/... all become NOT NULL once backfilled)
_TASK_LINKED_TABLES = [
    "projects",
    "tasks",
    "subtasks",
    "dependencies",
    "work_sessions",
    "calendar_events",
    "predictions",
]


def _ensure_placeholder_user(bind) -> int:
    uid = bind.execute(
        sa.text("SELECT id FROM users WHERE email = :email"), {"email": _PLACEHOLDER_EMAIL}
    ).scalar()
    if uid is not None:
        return uid

    result = bind.execute(
        sa.text(
            "INSERT INTO users (email, name, hashed_password, google_sub, "
            "google_picture_url, is_active, created_at, updated_at) "
            "VALUES (:email, :name, NULL, :google_sub, NULL, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"email": _PLACEHOLDER_EMAIL, "name": "Legacy data (pre-auth)", "google_sub": _PLACEHOLDER_GOOGLE_SUB},
    )
    return result.lastrowid


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "users" not in inspector.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=True),
            sa.Column("google_sub", sa.String(length=255), nullable=True),
            sa.Column("google_picture_url", sa.String(length=1000), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "hashed_password IS NOT NULL OR google_sub IS NOT NULL",
                name="ck_users_has_login_method",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("google_sub"),  # models/user.py declares unique=True (a constraint, not an index)
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    inspector = sa.inspect(bind)  # re-inspect: users may have just been created
    # An account created purely as a migration anchor is never meant to be
    # logged into -- users is a fresh table on a fresh install, so there is
    # nothing to backfill yet and no placeholder is needed.
    existing_tables = inspector.get_table_names()
    needs_placeholder = any(
        t in existing_tables and "user_id" not in {c["name"] for c in inspector.get_columns(t)}
        for t in _TASK_LINKED_TABLES
        if t in existing_tables
    )
    placeholder_id = _ensure_placeholder_user(bind) if needs_placeholder else None

    for table_name in _TASK_LINKED_TABLES:
        if table_name not in existing_tables:
            continue  # fresh DB: create_all() already built the current model shape

        existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
        if "user_id" in existing_columns:
            continue

        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

        bind.execute(
            sa.text(f'UPDATE "{table_name}" SET user_id = :uid WHERE user_id IS NULL'),
            {"uid": placeholder_id},
        )

        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("user_id", nullable=False)
            batch_op.create_foreign_key(
                f"fk_{table_name}_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
            )
            batch_op.create_index(f"ix_{table_name}_user_id", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    for table_name in reversed(_TASK_LINKED_TABLES):
        if table_name not in existing_tables:
            continue
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_user_id")
            batch_op.drop_constraint(f"fk_{table_name}_user_id_users", type_="foreignkey")
            batch_op.drop_column("user_id")

    if "users" in existing_tables:
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
