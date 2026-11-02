"""A place for each work order in its column of the board. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rank", sa.Integer(), server_default="0", nullable=False))
        batch_op.create_index(batch_op.f("ix_work_order_rank"), ["rank"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_order_rank"))
        batch_op.drop_column("rank")
