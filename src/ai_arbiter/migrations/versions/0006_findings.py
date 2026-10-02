"""Findings: scan runs, findings with evidence and reviews, suppressions, digest runs.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digest_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locales", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_digest_run_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digest_run")),
    )
    op.create_table(
        "scan_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("rulepack_version", sa.String(length=100), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_scan_run_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_run")),
    )
    op.create_table(
        "suppression",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_ref", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_suppression_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppression")),
    )
    op.create_table(
        "finding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("scan_run_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("rulepack_version", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message_key", sa.String(length=200), nullable=False),
        sa.Column("legal_refs", sa.JSON(), nullable=False),
        sa.Column("applies_from", sa.Date(), nullable=True),
        sa.Column("accepted_until", sa.Date(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_system_id"], ["ai_system.id"], name=op.f("fk_finding_ai_system_id_ai_system")
        ),
        sa.ForeignKeyConstraint(
            ["scan_run_id"], ["scan_run.id"], name=op.f("fk_finding_scan_run_id_scan_run")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_finding_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding")),
        sa.UniqueConstraint("tenant_id", "fingerprint", name=op.f("uq_finding_tenant_id")),
    )
    op.create_index("ix_finding_tenant_status", "finding", ["tenant_id", "status"], unique=False)

    op.create_table(
        "finding_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["finding.id"], name=op.f("fk_finding_evidence_finding_id_finding")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_finding_evidence_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_evidence")),
    )
    op.create_table(
        "finding_review",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=False),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["finding.id"], name=op.f("fk_finding_review_finding_id_finding")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_finding_review_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_review")),
    )


def downgrade() -> None:
    op.drop_table("finding_review")
    op.drop_table("finding_evidence")
    op.drop_index("ix_finding_tenant_status", table_name="finding")

    op.drop_table("finding")
    op.drop_table("suppression")
    op.drop_table("scan_run")
    op.drop_table("digest_run")
