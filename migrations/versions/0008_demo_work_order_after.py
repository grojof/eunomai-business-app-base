"""The work order each one waits for, for the planning's timeline. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.add_column(sa.Column("after_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_work_order_after_id"), ["after_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_work_order_after_id_work_order"), "work_order", ["after_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_work_order_after_id_work_order"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_work_order_after_id"))
        batch_op.drop_column("after_id")
