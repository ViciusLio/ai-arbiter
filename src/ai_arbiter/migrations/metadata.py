"""The complete schema: importing this module registers every ORM model.

Each package that owns tables is imported here when it is implemented, so migrations and
schema tests see one metadata object.
"""

from ai_arbiter.compliance.classifier.model import Classification, ClassificationReview
from ai_arbiter.compliance.findings.model import (
    DigestRun,
    Finding,
    FindingEvidence,
    FindingReview,
    ScanRun,
    Suppression,
)
from ai_arbiter.compliance.inventory.model import AISystem, AISystemRole
from ai_arbiter.core.audit.model import AuditChainHead, AuditEntry
from ai_arbiter.core.events.model import OutboxEvent
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.gateway.a2a.model import A2aAgent, A2aGrant
from ai_arbiter.gateway.finops.model import Budget, UsageRollup
from ai_arbiter.gateway.identity.model import ApiKey, Principal, Project, RoleBinding, Team
from ai_arbiter.gateway.mcp.model import McpGrant, McpServer, McpTool

target_metadata = Base.metadata

__all__ = [
    "A2aAgent",
    "A2aGrant",
    "AISystem",
    "AISystemRole",
    "ApiKey",
    "AuditChainHead",
    "AuditEntry",
    "Budget",
    "Classification",
    "ClassificationReview",
    "DigestRun",
    "Finding",
    "FindingEvidence",
    "FindingReview",
    "Interaction",
    "Invocation",
    "McpGrant",
    "McpServer",
    "McpTool",
    "OutboxEvent",
    "Principal",
    "Project",
    "RoleBinding",
    "ScanRun",
    "Suppression",
    "Team",
    "Tenant",
    "UsageRollup",
    "target_metadata",
]
