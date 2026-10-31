"""A version on each work order, so that two people editing one row find out. tools/remove_demo.py deletes this file."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("work_order", schema=None) as batch_op:
        batch_op.drop_column("version")
