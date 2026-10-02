"""Events: in-process bus with a transactional outbox (ADR-0016)."""

from ai_arbiter.core.events.bus import DispatchResult, InProcessEventBus
from ai_arbiter.core.events.model import Event, OutboxEvent

__all__ = ["DispatchResult", "Event", "InProcessEventBus", "OutboxEvent"]
