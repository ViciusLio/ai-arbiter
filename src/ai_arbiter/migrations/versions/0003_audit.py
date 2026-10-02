"""Audit log: chain head and entries.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_chain_head",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), nullable=False),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_audit_chain_head_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_audit_chain_head")),
    )
    op.create_table(
        "audit_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_audit_entry_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_entry")),
        sa.UniqueConstraint("tenant_id", "seq", name=op.f("uq_audit_entry_tenant_id")),
    )


def downgrade() -> None:
    op.drop_table("audit_entry")
    op.drop_table("audit_chain_head")
