"""scope settings/daily_plans/memory/metrics to a user

The second wave of the multi-user migration (0003 did tasks/projects).
These five tables have no task/project FK to derive ownership from --
they're user-level rollups and preferences -- so each gets its own
user_id, backfilled to the same placeholder account 0003 created.

Also replaces each table's old single-user uniqueness constraint
(one row per key / per date, globally) with a (user_id, ...) composite,
since two different users both having a "best_deep_work_hours" setting
or a daily plan for the same date is now the normal case, not a
collision.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLACEHOLDER_EMAIL = "legacy@local"

# table_name -> (old unique constraint name or None, new constraint name, unique columns besides user_id)
_TABLES = {
    "settings": ("uq_settings_key", "uq_settings_user_key", ["key"]),
    "daily_plans": (None, "uq_daily_plans_user_date", ["plan_date"]),  # was a plain unique= on the column
    "episodic_memory": (None, None, []),
    "semantic_memory": (None, None, []),
    "productivity_metrics": (
        "uq_productivity_metrics_date",
        "uq_productivity_metrics_user_date",
        ["date"],
    ),
}


def _placeholder_user_id(bind) -> int:
    uid = bind.execute(
        sa.text("SELECT id FROM users WHERE email = :email"), {"email": _PLACEHOLDER_EMAIL}
    ).scalar()
    if uid is None:
        raise RuntimeError(
            "Expected the placeholder user created by migration 0003 -- "
            "run migrations in order."
        )
    return uid


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    placeholder_id = None  # looked up lazily: a database whose tables already have user_id needs none

    for table_name, (old_unique, new_unique, unique_cols) in _TABLES.items():
        if table_name not in inspector.get_table_names():
            continue  # fresh DB: create_all() already built the current model shape

        existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
        if "user_id" in existing_columns:
            continue

        if placeholder_id is None:
            placeholder_id = _placeholder_user_id(bind)

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

            if old_unique:
                existing_uniques = {u["name"] for u in inspector.get_unique_constraints(table_name)}
                if old_unique in existing_uniques:
                    batch_op.drop_constraint(old_unique, type_="unique")

            if new_unique:
                batch_op.create_unique_constraint(new_unique, ["user_id", *unique_cols])

            if table_name == "daily_plans":
                # The baseline made ix_daily_plans_plan_date a UNIQUE index, i.e. one
                # plan per date across *all* users -- a second user starting their day
                # would hit an IntegrityError. The (user_id, plan_date) constraint above
                # is the real rule now, so the index goes back to a plain lookup index.
                unique_plan_date_index = any(
                    i["name"] == "ix_daily_plans_plan_date" and i.get("unique")
                    for i in inspector.get_indexes(table_name)
                )
                if unique_plan_date_index:
                    batch_op.drop_index("ix_daily_plans_plan_date")
                    batch_op.create_index("ix_daily_plans_plan_date", ["plan_date"], unique=False)


def downgrade() -> None:
    for table_name, (old_unique, new_unique, unique_cols) in _TABLES.items():
        with op.batch_alter_table(table_name) as batch_op:
            if new_unique:
                batch_op.drop_constraint(new_unique, type_="unique")
            if table_name == "daily_plans":
                batch_op.drop_index("ix_daily_plans_plan_date")
                batch_op.create_index("ix_daily_plans_plan_date", ["plan_date"], unique=True)
            if old_unique:
                batch_op.create_unique_constraint(old_unique, unique_cols)
            batch_op.drop_index(f"ix_{table_name}_user_id")
            batch_op.drop_constraint(f"fk_{table_name}_user_id_users", type_="foreignkey")
            batch_op.drop_column("user_id")
