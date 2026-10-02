"""Interactions: the group an external source assigns its requests to.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("interaction", sa.Column("source_group", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("interaction", "source_group")
