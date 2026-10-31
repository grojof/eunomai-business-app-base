"""The day a work order is planned for, for the planning screen. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.add_column(sa.Column("planned_on", sa.Date(), nullable=True))
        batch_op.create_index(batch_op.f("ix_work_order_planned_on"), ["planned_on"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_order_planned_on"))
        batch_op.drop_column("planned_on")
