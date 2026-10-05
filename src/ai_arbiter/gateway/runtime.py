"""Everything a gateway process needs, built once from the settings.

Plugins are loaded by name through the registry, so this module wires adapters without
importing them (ADR-0010, ADR-0011).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.plugins.registry import (
    AGENT_CARD_READERS,
    EVENT_BUSES,
    PII_DETECTORS,
    SECRET_STORES,
    PluginRegistry,
)
from ai_arbiter.core.ports import (
    AuditLog,
    EventBus,
    LLMProvider,
    NoSystemDirectory,
    PIIDetector,
    SecretStore,
    SystemDirectory,
)
from ai_arbiter.gateway.a2a.proxy import A2aProxy, load_a2a_pack
from ai_arbiter.gateway.a2a.registry import A2aRegistry
from ai_arbiter.gateway.chat import ChatService
from ai_arbiter.gateway.finops.budgets import BudgetService
from ai_arbiter.gateway.finops.catalogue import PriceCatalogue, load_catalogue
from ai_arbiter.gateway.finops.metering import UsageMeter
from ai_arbiter.gateway.identity.service import IdentityService, PepperRing
from ai_arbiter.gateway.llm_router.deployments import build_targets
from ai_arbiter.gateway.llm_router.router import Router
from ai_arbiter.gateway.mcp.catalogue import McpCatalogue
from ai_arbiter.gateway.mcp.proxy import McpProxy, load_mcp_pack
from ai_arbiter.gateway.policy.engine import RulePolicyEngine, load_policy_pack

SystemDirectoryFactory = Callable[[AuditLog, EventBus, Clock], SystemDirectory]


@dataclass
class GatewayRuntime:
    settings: Settings
    database: Database
    clock: Clock
    secrets: SecretStore
    identity: IdentityService
    audit: DatabaseAuditLog
    bus: EventBus
    router: Router
    catalogue: PriceCatalogue
    mcp: McpCatalogue
    mcp_proxy: McpProxy
    a2a: A2aRegistry
    a2a_proxy: A2aProxy
    meter: UsageMeter
    budgets: BudgetService
    detector: PIIDetector
    policy: RulePolicyEngine
    chat: ChatService
    providers: Mapping[str, LLMProvider]

    async def aclose(self) -> None:
        """Finish pending writes and close provider connections. Not the database."""
        await self.chat.drain()
        for provider in self.providers.values():
            await provider.aclose()
        await self.mcp_proxy.aclose()
        await self.a2a.aclose()
        await self.a2a_proxy.aclose()


async def build_runtime(
    settings: Settings,
    database: Database,
    *,
    registry: PluginRegistry | None = None,
    provider_options: dict[str, dict[str, Any]] | None = None,
    clock: Clock | None = None,
    systems: SystemDirectoryFactory | None = None,
    mcp_transport: Any = None,
    a2a_transport: Any = None,
) -> GatewayRuntime:
    """Validate the configuration against the installed plugins and build the services.

    Raises ``PluginError``, ``ConfigurationError``, ``RulePackError`` or
    ``SecretNotFoundError``: a gateway that cannot work fails here, not at the first
    request.
    """
    registry = registry if registry is not None else PluginRegistry()
    clock = clock if clock is not None else SystemClock()
    secrets: SecretStore = registry.load(SECRET_STORES, settings.plugins.secret_store)()
    bus: EventBus = registry.load(EVENT_BUSES, settings.plugins.event_bus)()
    detector: PIIDetector = registry.load(PII_DETECTORS, settings.plugins.pii_detector)()

    redaction_key: bytes | None = None
    if settings.redaction.key is not None:
        secret = await secrets.get(SecretRef.parse(settings.redaction.key))
        redaction_key = secret.get_secret_value().encode("utf-8")

    catalogue = load_catalogue(settings.finops)
    meter = UsageMeter(catalogue)
    targets, providers = build_targets(
        settings.deployments, registry, secrets, provider_options=provider_options
    )
    router = Router(targets, providers, settings.router, cost_of=meter.comparable_cost)
    budgets = BudgetService(catalogue.currency, settings.finops.reporting, clock)
    audit = DatabaseAuditLog(clock)
    policy = RulePolicyEngine(load_policy_pack(settings.policy))
    # The inventory belongs to the compliance toolkit, which the gateway does not import:
    # whoever composes the process passes a factory for the directory.
    directory = systems(audit, bus, clock) if systems is not None else None
    chat = ChatService(
        database=database,
        router=router,
        meter=meter,
        budgets=budgets,
        policy=policy,
        policy_settings=settings.policy,
        detector=detector,
        redaction=settings.redaction,
        redaction_key=redaction_key,
        audit=audit,
        bus=bus,
        default_fail_mode=settings.audit.fail_mode,
        clock=clock,
        systems=directory,
    )
    mcp_catalogue = McpCatalogue(allow_http_hosts=settings.mcp.allow_http_hosts, clock=clock)
    a2a_registry = A2aRegistry(
        reader=registry.load(AGENT_CARD_READERS, settings.plugins.agent_card_reader)(),
        settings=settings.a2a,
        clock=clock,
        transport=a2a_transport,
    )
    return GatewayRuntime(
        settings=settings,
        database=database,
        clock=clock,
        secrets=secrets,
        identity=IdentityService(PepperRing(settings.identity.api_key_pepper, secrets), clock),
        audit=audit,
        bus=bus,
        router=router,
        catalogue=catalogue,
        meter=meter,
        budgets=budgets,
        detector=detector,
        policy=policy,
        chat=chat,
        a2a=a2a_registry,
        a2a_proxy=A2aProxy(
            database=database,
            registry=a2a_registry,
            pack=load_a2a_pack(settings.a2a),
            audit=audit,
            secrets=secrets,
            settings=settings.a2a,
            systems=directory if directory is not None else NoSystemDirectory(),
            clock=clock,
            transport=a2a_transport,
        ),
        mcp=mcp_catalogue,
        mcp_proxy=McpProxy(
            database=database,
            catalogue=mcp_catalogue,
            pack=load_mcp_pack(settings.mcp),
            audit=audit,
            secrets=secrets,
            settings=settings.mcp,
            systems=directory if directory is not None else NoSystemDirectory(),
            clock=clock,
            transport=mcp_transport,
        ),
        providers=providers,
    )


async def preflight(settings: Settings) -> None:
    """Build the runtime and discard it, to report configuration errors before serving."""
    database = Database(settings.database.url)
    try:
        runtime = await build_runtime(settings, database)
        await runtime.aclose()
    finally:
        await database.dispose()
