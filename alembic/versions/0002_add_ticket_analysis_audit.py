"""add ticket analysis result and audit metadata

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("tickets", sa.Column("reasoning_tags", sa.JSON(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("analysis_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("provider_requested", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("provider_used", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("model_requested", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("model_used", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
    )
    op.add_column("tickets", sa.Column("fallback_used", sa.Boolean(), nullable=True))
    op.add_column("tickets", sa.Column("input_char_count", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("provider_attempts", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("repair_attempts", sa.Integer(), nullable=True),
    )
    op.add_column("tickets", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("error_category", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tickets", "analyzed_at")
    op.drop_column("tickets", "provider_request_id")
    op.drop_column("tickets", "error_category")
    op.drop_column("tickets", "latency_ms")
    op.drop_column("tickets", "output_tokens")
    op.drop_column("tickets", "input_tokens")
    op.drop_column("tickets", "repair_attempts")
    op.drop_column("tickets", "provider_attempts")
    op.drop_column("tickets", "input_char_count")
    op.drop_column("tickets", "fallback_used")
    op.drop_column("tickets", "prompt_version")
    op.drop_column("tickets", "model_used")
    op.drop_column("tickets", "model_requested")
    op.drop_column("tickets", "provider_used")
    op.drop_column("tickets", "provider_requested")
    op.drop_column("tickets", "analysis_status")
    op.drop_column("tickets", "reasoning_tags")
    op.drop_column("tickets", "confidence")
