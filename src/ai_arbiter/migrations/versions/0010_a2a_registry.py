"""A2A registry: agents with what their card said, and the grants to call them.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "a2a_agent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("card_url", sa.String(length=2000), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("credential", sa.String(length=200), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("card_name", sa.String(length=200), nullable=True),
        sa.Column("card_version", sa.String(length=50), nullable=True),
        sa.Column("card_sha256", sa.String(length=64), nullable=True),
        sa.Column("interfaces", sa.JSON(), nullable=False),
        sa.Column("verification", sa.String(length=20), nullable=False),
        sa.Column("signing_key_id", sa.String(length=200), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_system_id"], ["ai_system.id"], name=op.f("fk_a2a_agent_ai_system_id_ai_system")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_a2a_agent_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_a2a_agent")),
        sa.UniqueConstraint("tenant_id", "key", name=op.f("uq_a2a_agent_tenant_id")),
    )
    op.create_table(
        "a2a_grant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["a2a_agent.id"], name=op.f("fk_a2a_grant_agent_id_a2a_agent")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_a2a_grant_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_a2a_grant")),
        sa.UniqueConstraint(
            "agent_id", "scope_type", "scope_id", name=op.f("uq_a2a_grant_agent_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("a2a_grant")
    op.drop_table("a2a_agent")
