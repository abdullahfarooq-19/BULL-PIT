"""backtest

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("weeks", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("starting_cash", sa.String(), nullable=False),
        sa.Column("models", sa.JSON(), nullable=False),
        sa.Column("assets", sa.JSON(), nullable=False),
        sa.Column("git_commit", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_reason", sa.String(), nullable=True),
        sa.Column("checkpoint", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Nullable, so existing `requests` rows need no data migration.
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.String(), nullable=True))
        batch_op.create_index(batch_op.f("ix_requests_run_id"), ["run_id"], unique=False)
        batch_op.create_foreign_key("fk_requests_run_id", "backtest_runs", ["run_id"], ["id"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("recommended_shares", sa.Integer(), nullable=False),
        sa.Column("approved_shares", sa.Integer(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approvals_request_id"), "approvals", ["request_id"], unique=True)

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("client_order_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("submitted_on", sa.Date(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("reference_price", sa.String(), nullable=False),
        sa.Column("stop_loss", sa.String(), nullable=False),
        sa.Column("take_profit", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_price", sa.String(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.String(), nullable=True),
        sa.Column("exit_reason", sa.String(), nullable=True),
        sa.Column("cancel_reason", sa.String(), nullable=True),
        sa.Column("pnl", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trades_request_id"), "trades", ["request_id"], unique=True)
    op.create_index(op.f("ix_trades_run_id"), "trades", ["run_id"], unique=False)
    op.create_index(op.f("ix_trades_client_order_id"), "trades", ["client_order_id"], unique=True)

    op.create_table(
        "equity_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("cash", sa.String(), nullable=False),
        sa.Column("positions_value", sa.String(), nullable=False),
        sa.Column("equity", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "date", name="uq_equity_snapshots_run_date"),
    )
    op.create_index(
        op.f("ix_equity_snapshots_run_id"), "equity_snapshots", ["run_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_equity_snapshots_run_id"), table_name="equity_snapshots")
    op.drop_table("equity_snapshots")

    op.drop_index(op.f("ix_trades_client_order_id"), table_name="trades")
    op.drop_index(op.f("ix_trades_run_id"), table_name="trades")
    op.drop_index(op.f("ix_trades_request_id"), table_name="trades")
    op.drop_table("trades")

    op.drop_index(op.f("ix_approvals_request_id"), table_name="approvals")
    op.drop_table("approvals")

    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.drop_constraint("fk_requests_run_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_requests_run_id"))
        batch_op.drop_column("run_id")

    op.drop_table("backtest_runs")
