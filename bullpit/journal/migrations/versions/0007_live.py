"""live

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # SQLite can't alter an index, so the lock is dropped and recreated (M8-FR-11).
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.drop_index("uq_requests_running")
        batch_op.create_index(
            "uq_requests_running",
            ["ticker", "mode"],
            unique=True,
            sqlite_where=sa.text("status IN ('running', 'awaiting_approval')"),
        )

    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("latest_price", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("confirmations", sa.JSON(), nullable=True))

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("order_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("stop_order_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("take_profit_order_id", sa.String(), nullable=True))

    with op.batch_alter_table("equity_snapshots", schema=None) as batch_op:
        batch_op.alter_column("cash", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("positions_value", existing_type=sa.String(), nullable=True)
        batch_op.create_index(
            "uq_equity_snapshots_live_date",
            ["date"],
            unique=True,
            sqlite_where=sa.text("run_id IS NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("equity_snapshots", schema=None) as batch_op:
        batch_op.drop_index("uq_equity_snapshots_live_date")
        batch_op.alter_column("positions_value", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("cash", existing_type=sa.String(), nullable=False)

    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_column("take_profit_order_id")
        batch_op.drop_column("stop_order_id")
        batch_op.drop_column("order_id")

    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_column("confirmations")
        batch_op.drop_column("latest_price")

    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.drop_index("uq_requests_running")
        batch_op.create_index(
            "uq_requests_running",
            ["ticker", "mode"],
            unique=True,
            sqlite_where=sa.text("status = 'running'"),
        )
