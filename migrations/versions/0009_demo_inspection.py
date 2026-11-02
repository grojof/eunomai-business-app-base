"""The inspection team's visits, for the calendar. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.core.columns

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inspection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", app.core.columns.UtcDateTime(), nullable=False),
        sa.Column("ends_at", app.core.columns.UtcDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["equipment_id"], ["equipment.id"], name=op.f("fk_inspection_equipment_id_equipment"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection")),
    )
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_inspection_equipment_id"), ["equipment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_inspection_starts_at"), ["starts_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("inspection", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_inspection_starts_at"))
        batch_op.drop_index(batch_op.f("ix_inspection_equipment_id"))
    op.drop_table("inspection")
