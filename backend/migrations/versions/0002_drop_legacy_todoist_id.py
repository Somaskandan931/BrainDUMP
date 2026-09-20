"""drop legacy tasks.todoist_id

Databases created before Alembic -- and before Todoist sync was removed --
still carry `tasks.todoist_id` and its unique constraint `uq_tasks_todoist_id`.
The Task model no longer has either, so `alembic check` reports them as drift.

Databases created from the models (fresh installs, and everything stamped from
the 0001 baseline) never had the column, so every step here is conditional and
the migration is a no-op for them. Nothing reads the column: it was only used
by the removed Todoist reconciliation.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN = "todoist_id"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _COLUMN not in {c["name"] for c in inspector.get_columns("tasks")}:
        return

    uniques = [u["name"] for u in inspector.get_unique_constraints("tasks") if _COLUMN in u["column_names"]]
    indexes = [i["name"] for i in inspector.get_indexes("tasks") if _COLUMN in i["column_names"]]

    # SQLite can't drop a column that a constraint/index still references, so
    # remove those first; batch mode then rebuilds the table without the column.
    with op.batch_alter_table("tasks") as batch_op:
        for name in uniques:
            if name:
                batch_op.drop_constraint(name, type_="unique")
        for name in indexes:
            batch_op.drop_index(name)
        batch_op.drop_column(_COLUMN)


def downgrade() -> None:
    # Nothing to restore: the 0001 schema (and the models) never had this column.
    pass
