"""evaluation

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The server default makes every existing (M6) run a `bullpit` run.
    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("policy", sa.String(), server_default="bullpit", nullable=False)
        )
        batch_op.add_column(sa.Column("source_run_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_backtest_runs_source_run_id", "backtest_runs", ["source_run_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_backtest_runs_source_run_id", type_="foreignkey")
        batch_op.drop_column("source_run_id")
        batch_op.drop_column("policy")
