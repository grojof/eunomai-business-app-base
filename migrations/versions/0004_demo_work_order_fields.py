"""What the work order form asks for, beyond the planning screen. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("fault", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("priority", sa.String(length=8), server_default="normal", nullable=False))
        batch_op.add_column(sa.Column("crew", sa.Integer(), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("stop_needed", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_check_constraint(batch_op.f("ck_work_order_priority"), "priority IN ('low', 'normal', 'high')")


def downgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_work_order_priority"), type_="check")
        batch_op.drop_column("stop_needed")
        batch_op.drop_column("crew")
        batch_op.drop_column("priority")
        batch_op.drop_column("fault")
        batch_op.drop_column("description")
