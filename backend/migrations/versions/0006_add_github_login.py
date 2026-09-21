"""add github_id/github_avatar_url to users, widen the login-method check

Adds GitHub as a third login method alongside email/password and
Google Sign-In (see models/user.py, auth/github_login.py). Widens the
existing ck_users_has_login_method CHECK constraint to also accept
github_id IS NOT NULL, so a GitHub-only account isn't rejected as
"unusable" the way it would be under 0003's original two-method check.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CHECK = "hashed_password IS NOT NULL OR google_sub IS NOT NULL"
_NEW_CHECK = "hashed_password IS NOT NULL OR google_sub IS NOT NULL OR github_id IS NOT NULL"
_CONSTRAINT_NAME = "ck_users_has_login_method"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}
    existing_checks = {c["name"] for c in inspector.get_check_constraints("users")}

    # NOTE: batch_alter_table's `table_args=` kwarg does NOT replace a
    # named constraint already on the reflected table -- it only ever
    # *appends* extras, which previously left two constraints both
    # named ck_users_has_login_method on the rebuilt table (one from
    # the original 0003 schema, one from here) and broke the very next
    # downgrade. Explicitly dropping the old one by name and creating
    # the new one is what actually replaces it.
    with op.batch_alter_table("users") as batch_op:
        if "github_id" not in existing_columns:
            batch_op.add_column(sa.Column("github_id", sa.String(length=64), nullable=True))
        if "github_avatar_url" not in existing_columns:
            batch_op.add_column(sa.Column("github_avatar_url", sa.String(length=1000), nullable=True))

        if _CONSTRAINT_NAME in existing_checks:
            batch_op.drop_constraint(_CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT_NAME, _NEW_CHECK)

        existing_uniques = {u["name"] for u in inspector.get_unique_constraints("users")}
        if "uq_users_github_id" not in existing_uniques:
            try:
                batch_op.create_unique_constraint("uq_users_github_id", ["github_id"])
            except Exception:  # noqa: BLE001 - already unique via the column def on some dialects
                pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_uniques = {u["name"] for u in inspector.get_unique_constraints("users")}
    existing_checks = {c["name"] for c in inspector.get_check_constraints("users")}

    with op.batch_alter_table("users") as batch_op:
        if "uq_users_github_id" in existing_uniques:
            batch_op.drop_constraint("uq_users_github_id", type_="unique")

        if _CONSTRAINT_NAME in existing_checks:
            batch_op.drop_constraint(_CONSTRAINT_NAME, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT_NAME, _OLD_CHECK)

        batch_op.drop_column("github_avatar_url")
        batch_op.drop_column("github_id")
