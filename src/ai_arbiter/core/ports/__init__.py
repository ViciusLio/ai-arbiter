"""Ports: the interfaces behind which everything replaceable sits (ADR-0011).

Implementations live in ``ai_arbiter.adapters`` or in the module that owns the
capability, and are chosen by configuration. Ports are added here when the first module
that needs them is implemented; the full list is in ``docs/architecture/interfaces.md``.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.audit.chain import VerificationReport
from ai_arbiter.core.audit.log import AuditReceipt, AuditRecord
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.domain.time import Clock
from ai_arbiter.core.events.model import Event
from ai_arbiter.core.ports.llm import LLMProvider
from ai_arbiter.core.redaction.model import PIIDetector

E = TypeVar("E", bound=Event)
Handler = Callable[[E], Awaitable[None]]


class SecretStore(Protocol):
    async def get(self, ref: SecretRef) -> SecretStr:
        """Return the secret. Raises ``SecretNotFoundError`` if it does not exist."""
        ...


class EventBus(Protocol):
    async def publish(self, event: Event, *, session: AsyncSession) -> None:
        """Record the event in the caller's transaction (ADR-0016)."""
        ...

    def subscribe(self, event_type: type[E], handler: Handler[E]) -> None:
        """Register a handler. Handlers must be idempotent on the event id."""
        ...


class AuditLog(Protocol):
    async def append(
        self, session: AsyncSession, tenant_id: UUID, record: AuditRecord
    ) -> AuditReceipt:
        """Chain an entry in the caller's transaction (ADR-0017)."""
        ...

    async def verify(self, session: AsyncSession, tenant_id: UUID) -> VerificationReport:
        """Recompute the tenant's chain and report the first broken link."""
        ...

    def export(self, session: AsyncSession, tenant_id: UUID) -> AsyncIterator[str]:
        """The chain as JSON lines that can be verified without the database."""
        ...


__all__ = [
    "AuditLog",
    "Clock",
    "EventBus",
    "Handler",
    "LLMProvider",
    "PIIDetector",
    "SecretStore",
]
