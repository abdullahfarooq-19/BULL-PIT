"""debate_recommendations

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Both new columns are nullable, so SQLite can add them without a batch
    # table rebuild (unlike 0002's NOT NULL columns).
    op.add_column("requests", sa.Column("outcome", sa.String(), nullable=True))
    op.add_column("requests", sa.Column("no_trade_reason", sa.String(), nullable=True))

    op.create_table(
        "debate_turns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.Column("concessions", sa.JSON(), nullable=False),
        sa.Column("conviction", sa.Double(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("unsupported_count", sa.Integer(), nullable=False),
        sa.Column("over_word_limit", sa.Boolean(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_debate_turns_request_id"), "debate_turns", ["request_id"], unique=False
    )

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("exit_style", sa.String(), nullable=False),
        sa.Column("target_weight", sa.String(), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("decisive_evidence", sa.JSON(), nullable=False),
        sa.Column("reasoning", sa.String(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.Column("sized_order", sa.JSON(), nullable=True),
        sa.Column("blocked_reason", sa.String(), nullable=True),
        sa.Column("review_decision", sa.String(), nullable=True),
        sa.Column("review_reason", sa.String(), nullable=True),
        sa.Column("review_shares", sa.Integer(), nullable=True),
        sa.Column("review_clamped", sa.Boolean(), nullable=True),
        sa.Column("review_flagged", sa.Boolean(), nullable=True),
        sa.Column("final_order", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendations_request_id"), "recommendations", ["request_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recommendations_request_id"), table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index(op.f("ix_debate_turns_request_id"), table_name="debate_turns")
    op.drop_table("debate_turns")
    op.drop_column("requests", "no_trade_reason")
    op.drop_column("requests", "outcome")
