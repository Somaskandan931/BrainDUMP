"""add activity_log table

Backs the per-user audit trail (models/activity.py,
services/workspace/activity_service.py) and the "why did BrainDUMP move
this task?" history endpoints. Brand-new table, nothing to backfill --
history starts from the moment this ships.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "activity_log" in inspector.get_table_names():
        return

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(16), nullable=False, server_default="user"),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_activity_log_user_id_id", "activity_log", ["user_id", "id"])
    op.create_index(
        "ix_activity_log_user_entity", "activity_log", ["user_id", "entity_type", "entity_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_activity_log_user_entity", table_name="activity_log")
    op.drop_index("ix_activity_log_user_id_id", table_name="activity_log")
    op.drop_table("activity_log")
