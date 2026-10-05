"""A system may name several projects: a link table in place of one column (ADR-0059).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from ai_arbiter.core.domain.ids import new_id

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM = sa.table(
    "ai_system",
    sa.column("id", sa.Uuid()),
    sa.column("tenant_id", sa.Uuid()),
    sa.column("project_id", sa.Uuid()),
)


def upgrade() -> None:
    link = op.create_table(
        "ai_system_project",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_system_id"],
            ["ai_system.id"],
            name=op.f("fk_ai_system_project_ai_system_id_ai_system"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_ai_system_project_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_system_project")),
        sa.UniqueConstraint(
            "ai_system_id", "project_id", name=op.f("uq_ai_system_project_ai_system_id")
        ),
    )
    op.create_index(
        op.f("ix_ai_system_project_project_id"), "ai_system_project", ["project_id"], unique=False
    )
    named = (
        op.get_bind()
        .execute(
            sa.select(_SYSTEM.c.id, _SYSTEM.c.tenant_id, _SYSTEM.c.project_id).where(
                _SYSTEM.c.project_id.is_not(None)
            )
        )
        .all()
    )
    if named:
        op.bulk_insert(
            link,
            [
                {
                    "id": new_id(),
                    "tenant_id": tenant_id,
                    "ai_system_id": system_id,
                    "project_id": project_id,
                }
                for system_id, tenant_id, project_id in named
            ],
        )
    op.drop_column("ai_system", "project_id")


def downgrade() -> None:
    op.add_column("ai_system", sa.Column("project_id", sa.Uuid(), nullable=True))
    link = sa.table(
        "ai_system_project",
        sa.column("id", sa.Uuid()),
        sa.column("ai_system_id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
    )
    bind = op.get_bind()
    # One column holds one project: of several, the first by identifier is kept.
    kept: dict[object, object] = {}
    for system_id, project_id in bind.execute(
        sa.select(link.c.ai_system_id, link.c.project_id).order_by(link.c.id)
    ):
        kept.setdefault(system_id, project_id)
    for system_id, project_id in kept.items():
        bind.execute(
            sa.update(_SYSTEM).where(_SYSTEM.c.id == system_id).values(project_id=project_id)
        )
    op.drop_index(op.f("ix_ai_system_project_project_id"), table_name="ai_system_project")
    op.drop_table("ai_system_project")
