"""Tenant context carried by every unit of work (ADR-0015)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

# The standalone CLI works with a single implicit tenant.
LOCAL_TENANT_SLUG = "local"


class TenantContext(BaseModel):
    """Who is acting, and on behalf of which tenant.

    Fields beyond ``tenant_id`` are filled in by the identity module when a request is
    authenticated; they stay ``None`` in the standalone CLI.
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    principal_id: UUID | None = None
    team_id: UUID | None = None
    project_id: UUID | None = None
    ai_system_id: UUID | None = None
