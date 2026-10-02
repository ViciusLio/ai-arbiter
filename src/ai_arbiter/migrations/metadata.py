"""The complete schema: importing this module registers every ORM model.

Each package that owns tables is imported here when it is implemented, so migrations and
schema tests see one metadata object.
"""

from ai_arbiter.core.audit.model import AuditChainHead, AuditEntry
from ai_arbiter.core.events.model import OutboxEvent
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.gateway.finops.model import Budget, UsageRollup
from ai_arbiter.gateway.identity.model import ApiKey, Principal, Project, RoleBinding, Team

target_metadata = Base.metadata

__all__ = [
    "ApiKey",
    "AuditChainHead",
    "AuditEntry",
    "Budget",
    "Interaction",
    "OutboxEvent",
    "Principal",
    "Project",
    "RoleBinding",
    "Team",
    "Tenant",
    "UsageRollup",
    "target_metadata",
]
