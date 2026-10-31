"""Files attached to a work order. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.core.columns

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_order_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("stored_name", sa.String(length=32), nullable=False),
        sa.Column("media_type", sa.String(length=40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("added_at", app.core.columns.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_order.id"],
            name=op.f("fk_work_order_file_work_order_id_work_order"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order_file")),
        sa.UniqueConstraint("stored_name", name=op.f("uq_work_order_file_stored_name")),
    )
    with op.batch_alter_table("work_order_file", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_work_order_file_work_order_id"), ["work_order_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("work_order_file", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_order_file_work_order_id"))
    op.drop_table("work_order_file")
