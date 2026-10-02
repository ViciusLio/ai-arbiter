"""Tenant context carried by every unit of work (ADR-0015)."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# The standalone CLI works with a single implicit tenant.
LOCAL_TENANT_SLUG = "local"


class AccessRole(StrEnum):
    """What a principal may do inside a tenant. Not the AI Act roles of ADR-0007."""

    ADMIN = "admin"  # manages identity, budgets and settings; reads everything
    AUDITOR = "auditor"  # reads usage and the audit log, changes nothing
    DEVELOPER = "developer"  # calls the models


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
    roles: frozenset[AccessRole] = frozenset()
