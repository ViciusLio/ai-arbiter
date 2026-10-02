"""Built-in implementations must satisfy their ports.

The assignments below are checked by mypy: an implementation that drifts from its
``Protocol`` fails type-checking, not at runtime in production.
"""

from ai_arbiter.adapters.azure.openai import AzureOpenAIProvider
from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.adapters.mock.provider import MockProvider
from ai_arbiter.adapters.openai_compat.provider import OpenAICompatProvider
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.domain.time import SystemClock
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.ports import AuditLog, Clock, EventBus, LLMProvider, SecretStore


def test_built_in_implementations_satisfy_their_ports() -> None:
    clock: Clock = SystemClock()
    secret_store: SecretStore = EnvSecretStore({})
    event_bus: EventBus = InProcessEventBus()

    audit_log: AuditLog = DatabaseAuditLog()
    providers: list[LLMProvider] = [
        MockProvider(),
        OpenAICompatProvider(secret_store),
        AzureOpenAIProvider(secret_store),
    ]

    assert callable(audit_log.append)
    assert all(callable(provider.chat) for provider in providers)
    assert clock.now().tzinfo is not None
    assert callable(secret_store.get)
    assert callable(event_bus.publish)
