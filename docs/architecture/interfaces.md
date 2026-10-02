# Interfaces

Status: **accepted** on 2026-10-02 (Phase 1). Signatures are sketches to fix
responsibilities and dependencies; exact types are settled when each module is
implemented, and the code is the reference once it exists.

All ports are `typing.Protocol` classes in `ai_arbiter.core.ports`. Implementations live
in `adapters` or in the module that owns the capability, and are selected by
configuration (ADR-0011). A port is added to the code together with its first
implementation: so far `Clock`, `SecretStore`, `EventBus`, `AuditLog`, `LLMProvider`,
`PIIDetector`, `PolicyEngine`, `SystemDirectory`, `TelemetrySource` and `Notifier`.

## 0. Where the code differs from these sketches

Reviewed at the end of Phases 3 and 4 against what was built. The sketches below are kept as
written in Phase 1; this table is what changed.

| Sketch | In the code | Why |
|---|---|---|
| `TenantContext.roles: frozenset[Role]` | `frozenset[AccessRole]` (`admin`, `auditor`, `developer`) | `Role` already names what a server process does (ADR-0020) |
| `RuleMatch` without an outcome | `RuleMatch.outcome` added; `ConditionTrace` holds fact name, operator, the value written in the rule and `negated` | A decision is derived from the outcomes of its matches; the value a fact had is never recorded |
| `Decision` | `details` added: structured explanation that is not a rule match, such as a route plan | Routing has candidates and attempts, not rules |
| `RuleEngine` protocol with `load` and `evaluate` | Functions in `core.rules`: `load_rule_pack`, `load_packaged_pack`, `evaluate` | One implementation, no state: a protocol would have no second user |
| `AuditLog.append(ctx, record, session=...)`, `verify(tenant_id, from_seq)` | `append(session, tenant_id, record)`, `verify(session, tenant_id)` | The session comes first everywhere; partial verification waits for anchors (v0.1.x) |
| `PIIDetector.detect` | Also `describe()`: what each category validates and misses | ADR-0014 requires the limits to be shown to users |
| `LLMProvider.name`, `capabilities()` | `settings_model` and `aclose()`; no `capabilities()` | Settings validation is what ADR-0011 asks for; nothing reads capabilities yet |
| `Router.plan(request, profile, constraints)` | `Router.plan(model, allowed=...)`, then `complete` or `open_stream` | Constraints by risk class are deferrable (ADR-0009); `allowed` is where they will arrive |
| `RoutingStrategy` protocol | Two strategies inside `Router` | Same reason as `RuleEngine` |
| `UsageMeter.record(interaction, session=...)`, `BudgetGuard.status(ctx)` | `UsageMeter.record(session, interaction)`, `BudgetService.status(session, ctx)` | Naming and argument order |
| `PriceCatalogue.price(provider, model, region)` | As sketched, on a class, not a protocol | One implementation |
| `SystemDirectory.resolve(ctx, ai_system_id)` | `resolve(session, tenant_id, ai_system_id)`, returning tier, whether it was reviewed and the classification id; `NoSystemDirectory` when the toolkit is absent | Phase 4. Constraints are configuration by tier (`router.constraints`), not part of the profile |
| `Classifier.classify(system, pack, on=date)` | `classify(pack, facts, roles)`: the date is not an input | Obligations carry `applies_from`; whether one applies today is decided when it is shown |
| `Detector`, `LocalCollector`, `FindingService.report(candidate)` | `ScannerService.observe` computes facts per system; `FindingService.report(session, tenant_id, candidate, scan_run_id=...)` | One scanner over inventory and traffic; local collectors are deferrable |
| `DigestRenderer` protocol | `render_digest(model, locale=, output=)` | One implementation |
| `Notifier.send(message)` | As sketched, in `core.notification`, with `name` and `settings_model`; `file` and `smtp` in `adapters.local.notifiers` | Phase 4b. The file notifier is the default, so that nothing is sent until an operator names a server |
| `TelemetrySource` | `parse(payload) -> InteractionRecord` in `core.interaction`; `jsonl` and `litellm` in `compliance.ingest` | Phase 4b |
| Events | Published: `InteractionRecorded`, `SystemDeclared`, `SystemChanged`, `SystemClassified`. Consumed: the two system events, by the classifier | The others have no consumer yet |
| HTTP: `/api/v1/tenants` | Not implemented; `/api/v1/me`, `/principals`, `/audit/fail-mode` added | A key acts inside one tenant; tenants are created from the CLI |
| CLI | `arbiter keys`, `arbiter usage report`, `arbiter pii`, `arbiter audit`, `arbiter retention` added; `arbiter ingest`, `arbiter report`, `arbiter systems discover` and `arbiter demo` added in Phase 4b | The deferrable items the owner chose (ADR-0040) |

## 1. Shared types

```python
class TenantContext(BaseModel, frozen=True):
    tenant_id: UUID
    principal_id: UUID | None
    project_id: UUID | None
    team_id: UUID | None
    ai_system_id: UUID | None
    roles: frozenset[Role]


class ActorRole(StrEnum):  # AI Act operator roles (ADR-0007)
    PROVIDER = "provider"
    DEPLOYER = "deployer"
    IMPORTER = "importer"
    DISTRIBUTOR = "distributor"
    AUTHORISED_REPRESENTATIVE = "authorised_representative"
    PRODUCT_MANUFACTURER = "product_manufacturer"


class RiskTier(StrEnum):
    OUT_OF_SCOPE = "out_of_scope"
    PROHIBITED = "prohibited"
    HIGH_RISK = "high_risk"
    TRANSPARENCY = "transparency"
    MINIMAL = "minimal"
    UNDETERMINED = "undetermined"


class LegalRef(BaseModel, frozen=True):
    regulation: str  # "EU-AI-ACT", "EU-GDPR"
    article: str  # "50(1)", "5(1)(f)", "Annex III(4)(a)"


class SystemRiskProfile(BaseModel, frozen=True):
    ai_system_id: UUID
    tier: RiskTier
    roles: frozenset[ActorRole]
    classification_id: UUID | None  # None for unclassified or discovered systems
    constraints: Mapping[str, JsonValue]  # e.g. allowed regions, content logging required
```

## 2. Rules and decisions

One envelope for every automated outcome (policy, routing, budget, classification,
finding). It is what the audit log stores and what reports render.

```python
class RuleMatch(BaseModel, frozen=True):
    rule_id: str
    pack: str
    pack_version: str
    matched: Sequence[ConditionTrace]  # which conditions held, on which fact names
    legal_refs: Sequence[LegalRef]
    applies_from: date | None
    message_key: str


class Decision(BaseModel, frozen=True):
    id: UUID
    kind: DecisionKind  # policy | routing | budget | classification | finding
    outcome: str  # allow, deny, redact, route:<target>, tier:<x>, ...
    matches: Sequence[RuleMatch]
    input_digest: str  # hash of the facts; the facts themselves are not stored
    engine_version: str
    decided_at: datetime


class RuleEngine(Protocol):
    def load(self, pack: RulePackRef) -> RulePack: ...
    def evaluate(self, pack: RulePack, kind: RuleKind, facts: Facts) -> Sequence[RuleMatch]: ...
```

`Facts` is a flat mapping from dotted names to JSON values. Fact names are declared in
the rule pack schema; a rule that references an undeclared fact fails validation at load
time, not at evaluation time.

## 3. Core ports

```python
class SecretStore(Protocol):
    async def get(self, ref: SecretRef) -> SecretStr: ...


class EventBus(Protocol):
    async def publish(self, event: Event, *, session: AsyncSession) -> None: ...
    def subscribe(self, event_type: type[E], handler: Handler[E]) -> None: ...


class AuditLog(Protocol):
    async def append(
        self, ctx: TenantContext, record: AuditRecord, *, session: AsyncSession
    ) -> AuditReceipt: ...
    async def verify(self, tenant_id: UUID, *, from_seq: int = 0) -> VerificationReport: ...
    def export(self, tenant_id: UUID, *, from_seq: int = 0) -> AsyncIterator[AuditEntry]: ...


class PIIDetector(Protocol):
    name: str

    def detect(self, text: str, *, locale: str | None = None) -> Sequence[PIISpan]: ...


class SystemDirectory(Protocol):  # implemented by compliance.inventory
    async def resolve(self, ctx: TenantContext, ai_system_id: UUID | None) -> SystemRiskProfile: ...


class Notifier(Protocol):
    async def send(self, message: OutboundMessage) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
```

- `publish` and `append` take the caller's session so that the event or audit entry is
  committed with the business change, or not at all.
- When compliance modules are disabled, `SystemDirectory` is bound to a null
  implementation that returns an `UNDETERMINED` profile with default constraints.
- `PIISpan` carries category, offsets and confidence, never the matched text.

## 4. Gateway

```python
class LLMProvider(Protocol):
    name: str

    def capabilities(self) -> ProviderCapabilities: ...
    async def chat(self, request: ChatRequest, target: Deployment) -> ChatResponse: ...
    def stream(self, request: ChatRequest, target: Deployment) -> AsyncIterator[ChatChunk]: ...


class RoutingStrategy(Protocol):
    name: str  # "priority", "cost"

    def order(
        self, candidates: Sequence[Candidate], request: ChatRequest
    ) -> Sequence[Candidate]: ...


class Router(Protocol):
    async def plan(
        self, request: ChatRequest, profile: SystemRiskProfile, constraints: RouteConstraints
    ) -> RoutePlan: ...


class PolicyEngine(Protocol):
    async def evaluate(self, stage: PolicyStage, facts: Facts) -> Decision: ...


class UsageMeter(Protocol):
    async def record(self, interaction: InteractionRecord, *, session: AsyncSession) -> None: ...


class BudgetGuard(Protocol):
    async def status(self, ctx: TenantContext) -> BudgetStatus: ...


class PriceCatalogue(Protocol):
    version: str

    def price(self, provider: str, model: str, region: str | None) -> ModelPrice | None: ...
```

- `RoutePlan` is an ordered list of targets plus, for every candidate, why it was kept,
  excluded or placed where it is. It becomes a `Decision` of kind `routing`.
- `PolicyEngine` is the port named in the brief. The default implementation collects
  facts and delegates to `RuleEngine`; an OPA implementation can replace it (ADR-0012).
- `PolicyStage` is `pre_call` or `post_call`. A decision outcome is `allow`, `deny` or
  `redact`, with obligations such as "route only to EU regions".
- A missing price is not an error: the interaction is recorded with no cost and reported
  as unpriced.

## 5. Compliance

```python
class InteractionRecord(BaseModel, frozen=True):  # canonical record (ADR-0019)
    source: str
    source_record_id: str
    tenant_id: UUID
    ai_system_id: UUID | None
    project_id: UUID | None
    principal_id: UUID | None
    started_at: datetime
    duration_ms: int | None
    operation: str  # "chat", later "embeddings", "tool_call", "a2a_task"
    requested_model: str | None
    provider: str | None
    model: str | None
    region: str | None
    status: str
    input_tokens: int | None
    output_tokens: int | None
    usage_estimated: bool
    pii_categories: frozenset[str]
    prompt_fingerprint: str | None
    attributes: Mapping[str, JsonValue]  # source-specific extras, already minimised


class TelemetrySource(Protocol):
    name: str
    tested_against: str  # source versions the mapping was verified with

    def read(self, cursor: Cursor | None) -> AsyncIterator[tuple[InteractionRecord, Cursor]]: ...


class Classifier(Protocol):
    def classify(
        self, system: SystemFacts, pack: RulePack, *, on: date
    ) -> ClassificationResult: ...


class Detector(Protocol):  # scanner: code that produces facts and evidence
    name: str
    scope: ScanScope  # traffic | inventory | config | local

    async def collect(self, ctx: ScanContext) -> AsyncIterator[Observation]: ...


class LocalCollector(Protocol):  # local_agent
    name: str
    category: str

    def describe(self) -> CollectionPlan: ...  # exact paths; what is read, what is never read
    def collect(self, consent: Consent) -> Iterator[Observation]: ...


class FindingService(Protocol):
    async def report(self, candidate: FindingCandidate) -> Finding: ...
    async def transition(
        self,
        finding_id: UUID,
        to: FindingStatus,
        *,
        by: UUID,
        reason: str,
        suppress: SuppressionScope | None = None,
    ) -> Finding: ...


class DigestRenderer(Protocol):
    format: str  # "markdown", "html"

    def render(self, digest: DigestModel, *, locale: str) -> RenderedArtifact: ...
```

- `Classifier.classify` takes the date explicitly. The same system and rule pack give a
  different list of *applicable* obligations on 1 December 2027 and on 3 December 2027;
  making the date a parameter keeps the function pure and lets reports show "what applies
  today" and "what will apply".
- `Detector` and `LocalCollector` only observe. Whether an observation is a finding is
  decided by scan rules in the rule engine, so that judgement stays in versioned data.
- `LocalCollector.describe` must be callable without reading anything outside its own
  code; it is what the consent prompt shows.

## 6. Events

Published through `EventBus`; payloads carry identifiers, not content.

| Event | Published by | Consumed by |
|---|---|---|
| `InteractionRecorded` | gateway, ingest | inventory, finops, scanner |
| `SystemDeclared`, `SystemDiscovered`, `SystemChanged` | inventory | classifier, scanner |
| `SystemClassified` | classifier | scanner, digest, gateway cache invalidation |
| `BudgetThresholdReached` | finops | findings, digest |
| `PolicyDenied` | gateway | scanner, digest |
| `FindingOpened`, `FindingStatusChanged` | findings | digest |
| `ScanCompleted` | scanner | digest |

## 7. HTTP surface (v0.1)

| Area | Paths | Role |
|---|---|---|
| Data plane | `POST /v1/chat/completions`, `GET /v1/models` | `gateway` |
| Health | `GET /healthz`, `GET /readyz` | all |
| Identity | `/api/v1/tenants`, `/teams`, `/projects`, `/api-keys` | `admin` |
| FinOps | `/api/v1/usage`, `/budgets` | `admin` |
| Audit | `/api/v1/audit/entries`, `/audit/verify`, `/audit/export` | `admin` |
| Inventory | `/api/v1/systems`, `/systems/{id}/classifications` | `admin` |
| Findings | `/api/v1/findings`, `/findings/{id}/transitions`, `/suppressions` | `admin` |
| Scans and digests | `/api/v1/scans`, `/digests` | `admin` |
| Ingestion | `POST /api/v1/ingest/{source}` (v0.2) | `admin` |

Errors use one typed model (RFC 9457 problem details) and include the decision id when a
policy or budget decision caused the response.

## 8. CLI surface (v0.1)

```text
arbiter init                       create a local workspace (SQLite) and a starter config
arbiter serve --roles ...          start the HTTP application (needs the gateway extra)
arbiter worker                     run the outbox dispatcher and handlers
arbiter systems add|list|show      manage the inventory
arbiter classify [SYSTEM]          classify one or all systems
arbiter scan [local|traffic|config]
arbiter findings list|show|review  review workflow
arbiter ingest FILE --source ...   import external gateway records
arbiter digest run [--locale it]   build the digest
arbiter report system|audit        render reports
arbiter audit verify|export
arbiter demo                       load the simulation scenarios and walk through them
```

The CLI calls the same application services as the HTTP routers, directly against the
local database. A remote mode that talks to a server is planned for v0.2.
