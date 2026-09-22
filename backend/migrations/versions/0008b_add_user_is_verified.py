"""add users.is_verified

Backs email verification (services/email_service.py,
api/v1/auth.py's /verify-email/* and /password-reset/* routes). Existing
rows default to true on backfill -- every account that already exists
was created before this feature shipped and has been logging in fine,
so there's nothing to gate retroactively (config.EMAIL_VERIFICATION_REQUIRED
only matters for accounts created after this migration). New
email+password registrations set it false explicitly in code; the
server_default here is a schema-level safety net, not the operative
default.

Revision ID: 0008b
Revises: 0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008b"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "is_verified" in columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    # Backfill: existing accounts are treated as already verified (see
    # module docstring). New rows created after this point set the column
    # explicitly in application code, so the server_default above is only
    # ever exercised here and by any row inserted through raw SQL.
    op.execute("UPDATE users SET is_verified = true WHERE is_verified IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_verified")
