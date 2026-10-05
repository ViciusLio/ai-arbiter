"""MCP catalogue: servers, the tools they list, and the grants to call them.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_server",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("transport", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("credential", sa.String(length=200), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("protocol_versions", sa.JSON(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_system_id"], ["ai_system.id"], name=op.f("fk_mcp_server_ai_system_id_ai_system")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_mcp_server_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_server")),
        sa.UniqueConstraint("tenant_id", "key", name=op.f("uq_mcp_server_tenant_id")),
    )
    op.create_table(
        "mcp_grant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("tool", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["server_id"], ["mcp_server.id"], name=op.f("fk_mcp_grant_server_id_mcp_server")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_mcp_grant_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_grant")),
        sa.UniqueConstraint(
            "server_id", "scope_type", "scope_id", "tool", name=op.f("uq_mcp_grant_server_id")
        ),
    )
    op.create_table(
        "mcp_tool",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["server_id"], ["mcp_server.id"], name=op.f("fk_mcp_tool_server_id_mcp_server")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_mcp_tool_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_tool")),
        sa.UniqueConstraint("server_id", "name", name=op.f("uq_mcp_tool_server_id")),
    )


def downgrade() -> None:
    op.drop_table("mcp_tool")
    op.drop_table("mcp_grant")
    op.drop_table("mcp_server")
