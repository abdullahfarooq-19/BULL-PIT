"""request_lock_signals

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("analyst", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signals_request_id"), "signals", ["request_id"], unique=False)

    # SQLite can't add a NOT NULL column in place, so this batch recreates
    # the table (dev-plan.md sec10, plan sec10); `requests` is still empty
    # on every existing journal, so no data-migration step is needed.
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ticker", sa.String(), nullable=False))
        batch_op.add_column(sa.Column("status", sa.String(), nullable=False))
        batch_op.add_column(sa.Column("status_reason", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("route", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("warnings", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("config", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("git_commit", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("price_source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(), nullable=True))
        batch_op.create_index(
            "uq_requests_running",
            ["ticker", "mode"],
            unique=True,
            sqlite_where=sa.text("status = 'running'"),
        )


def downgrade() -> None:
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.drop_index("uq_requests_running")
        batch_op.drop_column("finished_at")
        batch_op.drop_column("price_source")
        batch_op.drop_column("git_commit")
        batch_op.drop_column("config")
        batch_op.drop_column("warnings")
        batch_op.drop_column("route")
        batch_op.drop_column("status_reason")
        batch_op.drop_column("status")
        batch_op.drop_column("ticker")

    op.drop_index(op.f("ix_signals_request_id"), table_name="signals")
    op.drop_table("signals")
