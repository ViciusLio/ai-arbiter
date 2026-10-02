"""Interactions, usage roll-ups and budgets.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("limit_amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("soft_threshold_percent", sa.Integer(), nullable=False),
        sa.Column("hard", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_budget_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget")),
        sa.UniqueConstraint(
            "tenant_id", "scope_type", "scope_id", "period", name=op.f("uq_budget_tenant_id")
        ),
    )
    op.create_table(
        "interaction",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("principal_id", sa.Uuid(), nullable=True),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("requested_model", sa.String(length=200), nullable=True),
        sa.Column("deployment", sa.String(length=200), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("streamed", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_estimated", sa.Boolean(), nullable=False),
        sa.Column("cost_estimate", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("price_version", sa.String(length=100), nullable=True),
        sa.Column("policy_outcome", sa.String(length=50), nullable=True),
        sa.Column("prompt_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("pii_categories", sa.JSON(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_interaction_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interaction")),
        sa.UniqueConstraint(
            "tenant_id", "source", "source_record_id", name=op.f("uq_interaction_tenant_id")
        ),
    )
    op.create_index(
        "ix_interaction_tenant_started", "interaction", ["tenant_id", "started_at"], unique=False
    )

    op.create_table(
        "usage_rollup",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("requests", sa.BigInteger(), nullable=False),
        sa.Column("denied", sa.BigInteger(), nullable=False),
        sa.Column("failed", sa.BigInteger(), nullable=False),
        sa.Column("unpriced", sa.BigInteger(), nullable=False),
        sa.Column("estimated", sa.BigInteger(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cost_estimate", sa.BigInteger(), nullable=False),
        sa.Column("estimated_cost", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_usage_rollup_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "scope_type", "scope_id", "day", "currency", name=op.f("pk_usage_rollup")
        ),
    )


def downgrade() -> None:
    op.drop_table("usage_rollup")
    op.drop_index("ix_interaction_tenant_started", table_name="interaction")

    op.drop_table("interaction")
    op.drop_table("budget")
