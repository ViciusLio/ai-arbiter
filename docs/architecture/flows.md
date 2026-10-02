# Flows

Status: **accepted** on 2026-10-02 (Phase 1). Flows are implemented from Phase 3 onwards.

## 1. Chat completion through the gateway

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as gateway.api
    participant ID as identity
    participant SD as SystemDirectory
    participant FIN as finops
    participant POL as policy
    participant R as llm_router
    participant P as LLMProvider
    participant AUD as audit
    participant DB as Database

    C->>API: POST /v1/chat/completions
    API->>ID: authenticate(api key)
    ID-->>API: principal, tenant, project, ai_system_id
    API->>SD: resolve(ai_system_id)
    SD-->>API: risk profile
    API->>FIN: budget_status(scopes)
    FIN-->>API: remaining, soft or hard limit state
    API->>POL: evaluate(pre_call, facts)
    POL-->>API: Decision

    alt denied
        API->>AUD: append(decisions)
        AUD->>DB: write entry
        API-->>C: 403 with decision id and reasons
    else allowed
        API->>R: plan(request, constraints)
        R-->>API: RoutePlan, ordered targets with reasons
        loop until a target succeeds or the plan is exhausted
            API->>P: chat(request)
            P-->>API: response or retryable error
        end
        API->>POL: evaluate(post_call, facts)
        POL-->>API: Decision
        API->>DB: one transaction: interaction, audit entries, outbox events
        API-->>C: response with decision id header
    end
```

Notes:

- `facts` for the pre-call evaluation: request attributes, the system's risk profile,
  budget state and PII detector results on the prompt.
- Constraints passed to the router come from the policy decision: allowed providers,
  models and regions for the system's risk class.
- The `RoutePlan` lists every candidate with the reason it was kept, excluded or ordered
  as it was; the plan is part of the audited decision.
- Redaction, when a policy requires it, modifies the request before it reaches the
  provider.

## 2. From traffic to digest

```mermaid
sequenceDiagram
    autonumber
    participant SRC as Source (gateway or ingest)
    participant BUS as events
    participant INV as inventory
    participant SCN as scanner
    participant FND as findings
    participant REV as Reviewer
    participant DIG as digest
    participant N as Notifier

    SRC->>BUS: InteractionRecorded
    BUS->>INV: handle
    INV->>INV: attribute to a declared system, or create a discovered one
    INV->>BUS: SystemDiscovered (first sighting only)
    BUS->>SCN: handle
    SCN->>SCN: collect facts, evaluate scan rules
    SCN->>FND: report(candidate finding, evidence)
    FND->>FND: fingerprint, deduplicate, apply suppressions
    FND->>BUS: FindingOpened
    REV->>FND: transition(confirm, false positive, accept, mitigate)
    FND->>BUS: FindingStatusChanged
    Note over DIG: scheduled, once a day
    DIG->>FND: findings and transitions in the period
    DIG->>INV: systems and classifications changed in the period
    DIG->>DIG: build model, render Markdown and HTML per locale
    DIG->>N: send (optional)
```

Scan rules that work on aggregates (for example "a system with a high-risk profile sent
traffic to a provider outside the EU") run on a schedule over the period rather than per
event.

## 3. Ingestion from an external gateway

```mermaid
sequenceDiagram
    autonumber
    participant X as External source (LiteLLM log, APIM logs)
    participant TS as TelemetrySource adapter
    participant ING as ingest
    participant DB as Database
    participant BUS as events

    X->>TS: raw records (file, push or pull)
    TS->>TS: map to InteractionRecord, drop or redact content
    TS->>ING: records
    ING->>ING: resolve tenant and system mapping
    ING->>DB: upsert on (source, source_record_id)
    ING->>BUS: InteractionRecorded
    Note over BUS: from here, flow 2 applies unchanged
```

## 4. Declaring and classifying a system

```mermaid
sequenceDiagram
    autonumber
    participant U as User (CLI or API)
    participant INV as inventory
    participant CLS as classifier
    participant RE as rules engine
    participant AUD as audit
    participant GW as gateway

    U->>INV: declare system (YAML or API): purpose, context, capabilities, roles
    INV->>CLS: classify(system facts)
    CLS->>RE: evaluate(ai-act rule pack, facts)
    RE-->>CLS: matched rules with trace
    CLS->>CLS: derive tier, obligations, application dates
    CLS->>AUD: append(classification decision)
    CLS-->>U: tier, rationale, articles, "applies from", disclaimer
    Note over GW: next request for this system
    GW->>INV: SystemDirectory.resolve
    INV-->>GW: risk profile from the latest classification
```

A classification is immutable. Changing a declared attribute, or loading a new rule pack
version, produces a new classification that supersedes the previous one; both remain
queryable.

Missing facts do not default silently. If a rule needs a fact that was not declared, the
result lists it under "information needed" and the tier is reported as undetermined for
that branch.

## 5. Local scan with consent

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as arbiter scan local
    participant COL as LocalCollector plugins
    participant SCN as scanner
    participant DB as SQLite

    U->>CLI: arbiter scan local
    CLI->>COL: describe()
    COL-->>CLI: categories, exact paths, what is read and what is never read
    CLI-->>U: show plan, ask consent per category
    U->>CLI: consent (or --yes with explicit --categories)
    CLI->>COL: collect(consent)
    COL-->>CLI: facts and evidence, secret values stripped
    CLI->>SCN: evaluate scan rules
    SCN->>DB: scan run with consent record, findings
    CLI-->>U: summary, with confirmation that nothing was sent anywhere
```

The local agent has no network code path. Sending results to a server is a separate,
explicit command planned for later.

## 6. Finding lifecycle

```mermaid
stateDiagram-v2
    [*] --> open
    open --> confirmed: reviewer confirms
    open --> false_positive: reviewer rejects, reason required
    open --> accepted: risk accepted, reason and expiry required
    confirmed --> mitigated: fix declared
    confirmed --> accepted: risk accepted
    mitigated --> open: detected again
    false_positive --> open: reopened
    accepted --> open: acceptance expired
```

- Every transition records who, when and why, and is written to the audit log.
- A `false_positive` transition can create a suppression scoped to the finding
  fingerprint, the system or the rule. Suppressions carry a reason and can expire.
- Per rule, the ratio of confirmed to false-positive findings is reported in the digest.
  That is the feedback loop of v0.1: it tells a human which rule to fix.
