"""Inventory and classification: AI systems, their roles, classifications and reviews.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("purpose", sa.String(length=2000), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("lifecycle", sa.String(length=20), nullable=False),
        sa.Column("owner_principal_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("models_used", sa.JSON(), nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_ai_system_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_system")),
        sa.UniqueConstraint("tenant_id", "key", name=op.f("uq_ai_system_tenant_id")),
    )
    op.create_table(
        "ai_system_role",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("basis", sa.String(length=500), nullable=False),
        sa.Column("since", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ai_system_id"],
            ["ai_system.id"],
            name=op.f("fk_ai_system_role_ai_system_id_ai_system"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_ai_system_role_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_system_role")),
        sa.UniqueConstraint("ai_system_id", "role", name=op.f("uq_ai_system_role_ai_system_id")),
    )
    op.create_table(
        "classification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("rulepack", sa.String(length=100), nullable=False),
        sa.Column("rulepack_version", sa.String(length=100), nullable=False),
        sa.Column("regulation_as_of", sa.Date(), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("obligations", sa.JSON(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("missing_facts", sa.JSON(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_system_id"],
            ["ai_system.id"],
            name=op.f("fk_classification_ai_system_id_ai_system"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_classification_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classification")),
    )
    op.create_index(
        "ix_classification_system", "classification", ["tenant_id", "ai_system_id"], unique=False
    )

    op.create_table(
        "classification_review",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("classification_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["classification.id"],
            name=op.f("fk_classification_review_classification_id_classification"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_classification_review_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classification_review")),
    )
    with op.batch_alter_table("api_key", schema=None) as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_api_key_ai_system_id_ai_system"), "ai_system", ["ai_system_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("api_key", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_api_key_ai_system_id_ai_system"), type_="foreignkey"
        )

    op.drop_table("classification_review")
    op.drop_index("ix_classification_system", table_name="classification")

    op.drop_table("classification")
    op.drop_table("ai_system_role")
    op.drop_table("ai_system")
