"""order box

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("order_type", sa.String(), nullable=False, server_default="market")
        )
        batch_op.add_column(sa.Column("entry_price", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("limit_price", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("stop_loss", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("take_profit", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("seen_price", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("overrides", sa.JSON(), nullable=True))

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("order_type", sa.String(), nullable=False, server_default="market")
        )
        batch_op.add_column(sa.Column("limit_price", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_column("limit_price")
        batch_op.drop_column("order_type")

    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_column("overrides")
        batch_op.drop_column("seen_price")
        batch_op.drop_column("take_profit")
        batch_op.drop_column("stop_loss")
        batch_op.drop_column("limit_price")
        batch_op.drop_column("entry_price")
        batch_op.drop_column("order_type")
