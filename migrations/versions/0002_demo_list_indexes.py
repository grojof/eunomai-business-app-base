"""Indexes for the equipment list: it sorts by name and by cost. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("equipment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_equipment_cost"), ["cost"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_name"), ["name"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("equipment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_equipment_name"))
        batch_op.drop_index(batch_op.f("ix_equipment_cost"))
