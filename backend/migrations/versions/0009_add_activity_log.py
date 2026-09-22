"""add activity_log table

Backs the audit trail / task-history feature (see
services/workspace/activity_service.py, models/activity.py,
api/v1/activity.py). Brand-new table, no existing data to backfill.

Revision ID: 0009
Revises: 0008b
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008b"
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
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(20), nullable=False, server_default="user"),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_activity_log_user_id", "activity_log", ["user_id"])
    op.create_index("ix_activity_log_action", "activity_log", ["action"])
    op.create_index("ix_activity_log_entity_type", "activity_log", ["entity_type"])
    op.create_index("ix_activity_log_entity_id", "activity_log", ["entity_id"])
    # The activity feed's dominant query pattern (list_activity in
    # activity_service.py): a user's rows newest-first, optionally
    # filtered to one entity or action.
    op.create_index("ix_activity_log_user_created", "activity_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_log_user_created", table_name="activity_log")
    op.drop_index("ix_activity_log_entity_id", table_name="activity_log")
    op.drop_index("ix_activity_log_entity_type", table_name="activity_log")
    op.drop_index("ix_activity_log_action", table_name="activity_log")
    op.drop_index("ix_activity_log_user_id", table_name="activity_log")
    op.drop_table("activity_log")
