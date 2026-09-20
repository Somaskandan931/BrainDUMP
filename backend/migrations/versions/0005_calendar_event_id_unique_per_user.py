"""make calendar_events.google_event_id unique per user, not globally

The baseline schema made google_event_id globally unique, which was fine
for one user. With per-user Google Calendar connections, an event a user
was invited to carries the same Google event id in every attendee's
calendar, so two Brain Dump users on the same meeting would collide
(IntegrityError) the moment the second one synced. Replaces it with a
(user_id, google_event_id) composite.

The baseline created the old constraint unnamed, which SQLite can't drop
by name in batch mode -- the naming_convention below gives the reflected
unnamed constraint a deterministic name to drop. Fresh databases built
from the current models already have the composite constraint, so this is
a no-op for them.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "calendar_events"
_NEW = "uq_calendar_events_user_google_event"
_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
_OLD_REFLECTED = "uq_calendar_events_google_event_id"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return

    uniques = inspector.get_unique_constraints(_TABLE)
    if any(u["name"] == _NEW for u in uniques):
        return  # already the composite shape
    has_old = any(u["column_names"] == ["google_event_id"] for u in uniques)

    with op.batch_alter_table(_TABLE, naming_convention=_NAMING) as batch_op:
        if has_old:
            batch_op.drop_constraint(_OLD_REFLECTED, type_="unique")
        batch_op.create_unique_constraint(_NEW, ["user_id", "google_event_id"])


def downgrade() -> None:
    with op.batch_alter_table(_TABLE, naming_convention=_NAMING) as batch_op:
        batch_op.drop_constraint(_NEW, type_="unique")
        batch_op.create_unique_constraint(_OLD_REFLECTED, ["google_event_id"])
