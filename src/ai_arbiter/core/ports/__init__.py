"""Ports: the interfaces behind which everything replaceable sits (ADR-0011).

Implementations live in ``ai_arbiter.adapters`` or in the module that owns the
capability, and are chosen by configuration. Ports are added here when the first module
that needs them is implemented; the full list is in ``docs/architecture/interfaces.md``.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.events.model import Event

E = TypeVar("E", bound=Event)
Handler = Callable[[E], Awaitable[None]]


class Clock(Protocol):
    def now(self) -> datetime: ...


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


__all__ = ["Clock", "EventBus", "Handler", "SecretStore"]
