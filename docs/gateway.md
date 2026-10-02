# The gateway

An OpenAI-compatible endpoint in front of your model providers. Every request is
authenticated, checked by policy, routed to a deployment, metered and written to a
hash-chained audit log. Prompt and completion text is never stored.

> Arbiter is a support tool. It does not provide legal advice.

Status: `0.1.0a1`, not published. The mock provider is exercised end to end by the test
suite. The OpenAI-compatible adapter was checked by hand against a local Ollama server;
the Azure OpenAI adapter is tested against a simulated HTTP transport and **has not been
run against a real endpoint**.

## Quickstart

No container, no cloud account. Needs the `gateway` extra. Nothing is published on PyPI
yet: from a clone, run `uv sync --all-extras` once and put `uv run` in front of each
`arbiter` command.

```bash
pip install --pre "ai-arbiter[gateway]"   # once the first release is published

arbiter init                                   # arbiter.yaml, a SQLite database, secrets in .env
arbiter keys create --name demo --role admin   # prints the API key once
arbiter serve                                  # http://127.0.0.1:8080
```

```bash
export ARBITER_KEY=arb_...

curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $ARBITER_KEY" -H "Content-Type: application/json" \
  -d '{"model": "mock-small", "messages": [{"role": "user", "content": "Write to mario.rossi@example.com"}]}'
```

The answer comes from the mock provider. The response headers say what the gateway did:

| Header | Content |
|---|---|
| `X-Arbiter-Interaction-Id` | The record of this request |
| `X-Arbiter-Decision-Id` | The policy decision, as written in the audit log |
| `X-Arbiter-Policy` | `allow` or `redact` |
| `X-Arbiter-Redacted` | Categories of personal data that were redacted in the prompt |
| `X-Arbiter-Budget` | `ok`, or `soft` when a budget is past its soft threshold |

Then look at what was recorded:

```bash
arbiter usage report              # Markdown; add --locale it for Italian
arbiter audit verify              # recomputes the hash chain
```

Interactive API documentation is at `http://127.0.0.1:8080/docs`.

Any client that speaks the OpenAI API works by pointing its base URL at
`http://127.0.0.1:8080/v1` and using an Arbiter key as the API key.

## What happens to a request

1. **Authentication.** The API key identifies tenant, project, principal and, optionally,
   an AI system. A revoked or expired key is refused at once.
2. **Budgets.** The state of every budget that covers the caller is read.
3. **Detection.** The prompt is scanned for personal data and credentials.
4. **Policy.** Facts about the request are evaluated against the policy rule pack. The
   outcome is `deny`, `redact` or `allow`.
5. **Routing.** The deployments that serve the model are ordered; the first one that
   answers wins. Failures that may be transient are retried, then the next deployment is
   tried.
6. **Recording.** One transaction writes the interaction (metadata only), the policy and
   routing decisions in the audit chain, the usage roll-ups and an outbox event.

No database transaction is open while a provider is being called.

## Configuration

Everything is in `arbiter.yaml`; every key can be overridden by an environment variable
(`ARBITER_` prefix, `__` between nested keys). Secrets are never written in the file:
they are referenced as `secret://NAME` and read from `ARBITER_SECRET_NAME`, in the
environment or in `.env`.

### Deployments

A deployment is one place a model can be called.

```yaml
deployments:
  - name: azure-gpt4o-we          # unique; appears in usage and audit records
    provider: azure_openai        # plugin: mock, openai_compat, azure_openai
    model: gpt-4o-prod            # the name at the provider; for Azure, the deployment name
    serves: [gpt-4o]              # names clients may ask for; default: the model name
    region: westeurope
    priority: 10                  # lower is tried first
    priced_as: gpt-4o             # catalogue entry that prices it; default: the model name
    settings:
      endpoint: https://my-resource.openai.azure.com
      api_version: "2024-10-21"
      api_key: secret://azure-openai-key

  - name: local-ollama
    provider: openai_compat
    model: llama3.1
    serves: [gpt-4o, llama3.1]
    priority: 50
    usage_fallback: estimate      # see "Token counts" below
    settings:
      base_url: http://127.0.0.1:11434/v1
```

| Provider | Settings |
|---|---|
| `mock` | `reply`, `echo`, `latency_ms`, `fail` (`never`, `retryable`, `fatal`), `fail_first`, `report_usage`, `break_stream_after` |
| `openai_compat` | `base_url` (up to and including `/v1`), `api_key` (a secret reference, optional), `timeout_seconds` |
| `azure_openai` | `endpoint`, `api_version`, `api_key` (a secret reference), `timeout_seconds` |

Unknown plugins, invalid settings and missing secrets are reported when `arbiter serve`
starts, not at the first request.

### Routing

```yaml
router:
  strategy: priority      # or cost: cheapest first, by the price catalogue
  max_attempts: 3         # deployments tried for one request
  retries: 1              # extra calls to the same deployment after a transient failure
  retry_backoff_ms: 200
```

`router.constraints` limits the deployments and regions that systems of a risk tier may
use; see [the compliance toolkit](compliance.md). To attribute traffic to a declared
system, issue its key with `arbiter keys create --system KEY`.

A provider answer of 400 or 422 means the request itself is at fault: it is not retried
and not sent elsewhere. For a stream, retry and fallback happen only until the first
chunk arrives.

### Prices and cost

Prices are per million tokens, written as strings, never as numbers (ADR-0030).

```yaml
finops:
  prices:
    - provider: azure_openai
      model: gpt-4o
      region: westeurope          # optional; a regional price wins over a general one
      input_per_million: "2.50"
      output_per_million: "10.00"
      cached_input_per_million: "1.25"
  reporting:                      # optional: also show amounts in another currency
    currency: EUR
    rate: "0.92"                  # EUR per unit of the catalogue's currency
    rate_as_of: 2026-10-01
```

- **Arbiter ships no prices for real providers.** They change without notice, and a stale
  price shown as current would mislead. Enter the prices of the deployments you use; the
  catalogue shipped with the package prices only the mock provider, with invented
  figures.
- Every cost is an **estimate**, not an invoice. It is computed once, when the
  interaction is recorded, and stored with the version of the catalogue that produced it.
- A model with no price is metered and reported as *unpriced*.

### Token counts

When a provider returns no usage, the token counts stay unknown and the interaction is
unpriced (ADR-0031). The usage report shows how many such requests there were.

A deployment can set `usage_fallback: estimate` to estimate tokens from the length of the
text (`chars_per_token`, default 4). Estimated interactions are flagged and reported
apart. Hard budgets count what is recorded: without the estimate, traffic with unknown
usage does not consume budget.

### Budgets

```bash
curl -X POST http://127.0.0.1:8080/api/v1/budgets \
  -H "Authorization: Bearer $ARBITER_KEY" -H "Content-Type: application/json" \
  -d '{"scope_type": "project", "scope_id": "<project id>", "period": "month",
       "limit_amount": "50.00", "soft_threshold_percent": 80, "hard": true}'
```

From the command line, on the local database:

```bash
arbiter budgets create --limit 50 --hard                 # on the tenant, per month
arbiter budgets create --system cv-screening --limit 10.50 --period day
arbiter budgets create --scope project --id <project id> --limit 20
arbiter budgets list                                     # with what was spent so far
arbiter budgets delete 1a2b3c4d                          # the id, or its first characters
```

- Scopes: `tenant`, `team`, `project`, `principal`, `ai_system`. Periods: `day`, `month`.
- A **soft** budget reports (`X-Arbiter-Budget: soft`, and `GET /api/v1/budgets`). A
  **hard** budget denies requests once the limit is reached.
- A burst of concurrent requests can overshoot a hard limit slightly: each request reads
  what was spent before any of them is recorded.

### Policy

The default policy is a rule pack shipped with the package:

| Rule | When | Outcome |
|---|---|---|
| `POL-MODEL-NOT-ALLOWED` | The model is not in `policy.allowed_models` | deny |
| `POL-SYSTEM-PROHIBITED` | The API key belongs to a system classified as a prohibited practice | deny |
| `POL-BUDGET-EXCEEDED` | A hard budget that covers the request is used up | deny |
| `POL-PII-REDACT` | The detectors found personal data or credentials in the prompt | redact |

```yaml
policy:
  allowed_models: [gpt-4o, mock-small]   # omit to allow every model a deployment serves
  pack: ./my-policy.yaml                 # optional: replace the default pack
```

A rule pack is data: conditions are trees of `all`, `any` and `not` over comparisons of
named facts (`eq`, `ne`, `in`, `contains`, `gt`, `lt`, `exists`). Nothing in a pack is
executed (ADR-0012). The facts available to policy rules:

| Fact | Type |
|---|---|
| `request.model` | string |
| `request.model_allowed` | boolean |
| `request.stream` | boolean |
| `budget.hard_exceeded`, `budget.soft_exceeded` | boolean |
| `pii.detected` | boolean |
| `pii.categories` | list |
| `system.declared` | boolean: the API key is tied to an AI system |
| `system.tier` | string: the effective tier of that system's classification, when the compliance toolkit runs in the same process |
| `system.reviewed` | boolean: a person confirmed or overrode that classification |

A denied request returns 403 with the decision id and the rules that matched, in English
or Italian according to `Accept-Language`.

### Detection and redaction

Run `arbiter pii detectors` for the list below as the installed version sees it, and
`arbiter pii redact FILE` to try it on a text.

| Category | What is validated | What is missed |
|---|---|---|
| `email` | Address syntax | Obfuscated addresses; non-ASCII addresses |
| `phone` | International numbers with `+` (E.164); Italian mobile numbers; Italian landlines after a word such as "tel" | National formats of other countries; numbers in words |
| `iban` | Country and length for the SEPA area, mod-97 check | IBANs outside SEPA; lowercase; national account formats |
| `payment_card` | 13 to 19 digits, Luhn check | Numbers split across lines; expiry dates and security codes |
| `it_fiscal_code` | Structure and check character of the Italian *codice fiscale* | Codes with a typing error |
| `it_vat_number` | Italian *partita IVA* with its check digit, after `IT` or words such as "P.IVA" | The same number with nothing saying what it is; other countries |
| `ip_address` | IPv4 and IPv6 literals | Host names |
| `secret` | Private key blocks, JSON Web Tokens, keys with well-known prefixes | Passwords; credentials with no recognisable format |

**The built-in detectors recognise formats, not meaning. They do not detect names,
postal addresses, dates of birth, health data or any personal data written as free
text.** Identity documents and the phone and VAT formats of other member states arrive in
v0.1.x (ADR-0027). Precision and recall have not been measured yet. Treat redaction as a
reduction of exposure, not as a guarantee.

```yaml
redaction:
  default_strategy: mask          # mask: [EMAIL]; hash: [EMAIL:1f3a9c2e]; drop
  strategies:
    iban: hash
  key: secret://redaction-key     # needed for hash, and for prompt fingerprints
```

`hash` gives the same tag to the same value within a tenant, with a keyed digest, so that
a conversation stays coherent without exposing the value. With `redaction.key` set, each
interaction also stores a keyed fingerprint of the prompt, which allows repeated prompts
to be counted without storing them (ADR-0018).

Detection runs on the prompt, before the provider is called. Completions are not
scanned: post-call evaluation is planned for v0.1.x.

### Audit

See [the audit log](audit.md) for the chain, its verification and `audit.fail_mode`.

## Roles

| Role | May |
|---|---|
| `developer` | Call `/v1` |
| `auditor` | Read usage, budgets and the audit log |
| `admin` | Everything, including identity and budgets |

A role is granted to a principal on the tenant, a team or a project, and holds for keys
of that principal in the projects it covers.

A process serves only the parts its roles name: `arbiter serve --roles gateway` exposes
`/v1`, `--roles admin` exposes `/api/v1`.

## API keys

`arb_<key id>_<secret><checksum>` (ADR-0028). The key id is public and identifies the key
in lists and audit entries. The database holds an HMAC of the key, keyed with a pepper
from the secret store; the key is shown once, when it is issued.

To rotate the pepper, add a second entry and make it active. Keys issued earlier keep
working until they are reissued:

```yaml
identity:
  api_key_pepper:
    active: "2"
    secrets:
      "1": secret://api-key-pepper
      "2": secret://api-key-pepper-2
```

## Errors

RFC 9457 problem details, with an `error` object in the shape OpenAI clients read.

| Status | `code` | Meaning |
|---|---|---|
| 401 | `invalid_api_key` | No key, or a key that is not valid |
| 403 | `permission_denied` | The key lacks the role |
| 403 | `policy_denied` | Stopped by policy; `decision_id`, `interaction_id` and `reasons` are included |
| 404 | `model_not_found` | No deployment serves the model |
| 409 | `conflict` | The change contradicts something that exists |
| 422 | `invalid_request` | The body is not valid; the rejected input is not echoed |
| 502 | `upstream_error` | Every deployment that was tried failed; `decision_id` is included |
| 503 | `audit_unavailable` | The request could not be recorded and the fail mode is `closed` |

## A real model for a demo

The mock provider answers with a fixed sentence. For a demo with a real model, run a
local OpenAI-compatible server and point a deployment at it (ADR-0039):

```bash
docker run -d --name arbiter-ollama -p 127.0.0.1:11434:11434 ollama/ollama
docker exec arbiter-ollama ollama pull smollm2:135m
```

```yaml
deployments:
  - name: ollama-local
    provider: openai_compat
    model: "smollm2:135m"
    serves: [small]
    settings:
      base_url: http://127.0.0.1:11434/v1
```

Remove it afterwards (`docker rm -f -v arbiter-ollama && docker rmi ollama/ollama`): the
image is 9.3 GB. With a local server nothing leaves the machine. With a hosted provider,
prompts are sent to that provider after redaction: say so to whoever uses the gateway.

## Performance

`scripts/measure_latency.py` measures the time the gateway adds to a request, against the
mock provider, in process. Measured on 2026-10-02 in a 2-core GitHub Codespace:

| Database | Concurrency | p50 | p95 |
|---|---:|---:|---:|
| SQLite | 1 | 18 ms | 27 ms |
| PostgreSQL | 1 | 17 ms | 27 ms |
| SQLite | 10 | 143 ms | 366 ms |
| PostgreSQL | 10 | 294 ms | 402 ms |

The numbers under concurrency are for requests of **one tenant**: the audit chain puts
the writes of a tenant in order (ADR-0017), so they queue. Nothing has been tuned yet;
the request path makes seventeen database statements.

## Limits of this release

- Chat completions only: no embeddings, no other endpoints.
- Post-call policy, external anchoring of the audit chain and the opt-in store of
  redacted content are planned for v0.1.x (ADR-0009).
- No cache of key lookups: every request reads the key, which is what makes revocation
  immediate.
- One reporting currency, at a fixed configured rate.
- Tenants are created from the command line; the API acts inside the tenant of its key.
