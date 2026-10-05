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

from ai_arbiter.core.agents import AgentCardReader
from ai_arbiter.core.audit.chain import VerificationReport
from ai_arbiter.core.audit.log import AuditReceipt, AuditRecord
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.domain.risk import SystemRiskProfile
from ai_arbiter.core.domain.time import Clock
from ai_arbiter.core.events.model import Event
from ai_arbiter.core.interaction import TelemetrySource
from ai_arbiter.core.notification import Notifier
from ai_arbiter.core.ports.llm import LLMProvider
from ai_arbiter.core.redaction.model import PIIDetector
from ai_arbiter.core.rules.decision import Decision
from ai_arbiter.core.rules.engine import Facts
from ai_arbiter.core.targets import NoTargetDirectory, TargetDirectory

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


class SystemDirectory(Protocol):
    """Tells the gateway how the system behind a request is classified.

    Implemented by the inventory of the compliance toolkit. Without it the gateway uses
    ``NoSystemDirectory``, for which every system is undetermined.

    A key tied to a system names it. A key tied to none belongs to the system that names
    the key's project, when exactly one declared system does (ADR-0059).
    """

    async def resolve(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        ai_system_id: UUID | None,
        project_id: UUID | None = None,
    ) -> SystemRiskProfile: ...


class NoSystemDirectory:
    """The directory of a gateway that runs without the compliance toolkit."""

    async def resolve(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        ai_system_id: UUID | None,
        project_id: UUID | None = None,
    ) -> SystemRiskProfile:
        return SystemRiskProfile(ai_system_id=ai_system_id)


class PolicyEngine(Protocol):
    """Decides what happens to a request from facts about it.

    The default implementation evaluates a rule pack; another engine, such as OPA, can
    take its place (ADR-0012). ``stage`` is ``pre_call`` or ``post_call``.
    """

    async def evaluate(self, stage: str, facts: Facts) -> Decision: ...


__all__ = [
    "AgentCardReader",
    "AuditLog",
    "Clock",
    "EventBus",
    "Handler",
    "LLMProvider",
    "NoSystemDirectory",
    "NoTargetDirectory",
    "Notifier",
    "PIIDetector",
    "PolicyEngine",
    "SecretStore",
    "SystemDirectory",
    "TargetDirectory",
    "TelemetrySource",
]
