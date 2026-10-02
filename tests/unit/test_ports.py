"""Built-in implementations must satisfy their ports.

The assignments below are checked by mypy: an implementation that drifts from its
``Protocol`` fails type-checking, not at runtime in production.
"""

from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.domain.time import SystemClock
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.ports import Clock, EventBus, SecretStore


def test_built_in_implementations_satisfy_their_ports() -> None:
    clock: Clock = SystemClock()
    secret_store: SecretStore = EnvSecretStore({})
    event_bus: EventBus = InProcessEventBus()

    assert clock.now().tzinfo is not None
    assert callable(secret_store.get)
    assert callable(event_bus.publish)
