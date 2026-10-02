"""Audit log: a hash chain per tenant, verifiable and exportable (ADR-0017)."""

from ai_arbiter.core.audit.chain import VerificationReport, genesis_hash, verify_export
from ai_arbiter.core.audit.log import (
    AuditReceipt,
    AuditRecord,
    DatabaseAuditLog,
    FailMode,
    set_tenant_fail_mode,
    tenant_fail_mode,
)
from ai_arbiter.core.audit.model import AuditChainHead, AuditEntry

__all__ = [
    "AuditChainHead",
    "AuditEntry",
    "AuditReceipt",
    "AuditRecord",
    "DatabaseAuditLog",
    "FailMode",
    "VerificationReport",
    "genesis_hash",
    "set_tenant_fail_mode",
    "tenant_fail_mode",
    "verify_export",
]
