"""The demo's equipment and work orders. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.core.columns

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("location", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("next_inspection", sa.Date(), nullable=False),
        sa.Column("cost", app.core.columns.ExactDecimal(), nullable=False),
        sa.Column("updated_at", app.core.columns.UtcDateTime(), nullable=False),
        sa.CheckConstraint("status IN ('in_service', 'due_soon', 'stopped')", name=op.f("ck_equipment_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment")),
        sa.UniqueConstraint("code", name=op.f("uq_equipment_code")),
    )
    with op.batch_alter_table("equipment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_equipment_location"), ["location"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_next_inspection"), ["next_inspection"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_status"), ["status"], unique=False)

    op.create_table(
        "work_order",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("hours", app.core.columns.ExactDecimal(), nullable=False),
        sa.Column("cost", app.core.columns.ExactDecimal(), nullable=False),
        sa.Column("opened_at", app.core.columns.UtcDateTime(), nullable=False),
        sa.Column("closed_at", app.core.columns.UtcDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('reported', 'planned', 'in_progress', 'checked', 'closed')", name=op.f("ck_work_order_status")
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["equipment.id"], name=op.f("fk_work_order_equipment_id_equipment"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order")),
    )
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_work_order_equipment_id"), ["equipment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_work_order_status"), ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("work_order")
    op.drop_table("equipment")
