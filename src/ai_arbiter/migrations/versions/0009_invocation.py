"""Invocations: one row per call to a tool or an agent through Arbiter.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("principal_id", sa.Uuid(), nullable=True),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("protocol", sa.String(length=10), nullable=False),
        sa.Column("target", sa.String(length=100), nullable=False),
        sa.Column("target_known", sa.Boolean(), nullable=False),
        sa.Column("method", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("streamed", sa.Boolean(), nullable=False),
        sa.Column("request_bytes", sa.Integer(), nullable=False),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_invocation_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invocation")),
    )
    op.create_index(
        "ix_invocation_tenant_started", "invocation", ["tenant_id", "started_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_invocation_tenant_started", table_name="invocation")
    op.drop_table("invocation")
