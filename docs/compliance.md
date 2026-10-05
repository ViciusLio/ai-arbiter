# The compliance toolkit

An inventory of the AI systems an organisation runs, an indicative classification of each
under the EU AI Act, a scanner that compares what was declared with what the gateway
saw, findings that a person reviews, and a daily digest. It works offline from the
command line, on SQLite, with or without the gateway.

> Arbiter is a support tool. It does not provide legal advice. A classification is
> **indicative**: it says what the declared facts lead to under the rules of the pack, and
> it is a proposal until a named person confirms or overrides it. An output with no
> findings says "no findings", never that a system satisfies the Regulation.

Status: `0.1.0a1`, not published. The rule pack was written from the Official Journal
texts retrieved from the Publications Office of the EU; **its comparison with EUR-Lex by
the project owner is still pending**, and every output says so until it is done
(ADR-0034).

## Quickstart

Nothing is published on PyPI yet: from a clone, run `uv sync --all-extras` once and put
`uv run` in front of each command.

```bash
arbiter init
arbiter systems apply -f examples/systems.yaml   # declare and classify seven invented systems
arbiter systems list
arbiter systems show cv-screening                # tier, obligations, provisions, dates
arbiter systems questions marketing-copy-generator   # what is still to answer
arbiter scan                                     # compare declarations, classification, traffic
arbiter findings list
arbiter digest run --locale it                   # or: --locale all --format both -o out/
arbiter report system cv-screening               # everything recorded about one system
arbiter report audit                             # the audit log of the last 30 days
```

Everything is also available over HTTP under `/api/v1` when `arbiter serve` runs; see
`/docs` on the server.

## Declaring a system

A declaration is YAML. `examples/systems.yaml` is a complete example.

```yaml
systems:
  - key: cv-screening                 # stable identifier, chosen by you
    name: CV screening
    purpose: Ranks job applications for the recruiters of the HR department.
    lifecycle: production             # planned, development, production, retired
    roles:
      - { role: deployer, basis: "Module of the HR suite bought from a vendor" }
    models:
      - { provider: openai_compat, model: vendor-ranker-2 }
    facts:
      scope.is_ai_system: true
      annex3.employment: true
      annex3.employment_recruitment: true
```

- **Roles** are the operator roles of the AI Act: `provider`, `deployer`, `importer`,
  `distributor`, `authorised_representative`, `product_manufacturer`. An organisation can
  hold several for one system. This version evaluates the obligations of a **deployer**;
  other roles are stored and reported as not covered.
- **Facts** are answers to the questions of the rule pack. `arbiter systems facts` lists
  them all with the provision each comes from. A fact that is left out is *not answered*,
  which is different from `false`.
- `fact_sets` at the top of a file hold answers shared by several systems; a system
  takes them with `use: [name, ...]`.
- A fact that no rule pack knows is refused: a misspelt name would otherwise sit unused
  while the real question stays unanswered.
- `arbiter systems apply` is safe to repeat: an unchanged system is left alone.

To attribute gateway traffic to a system, issue its API key with
`arbiter keys create --name NAME --system KEY`.

## How a system is classified

The classifier is deterministic: the same facts and the same rule pack always give the
same result, and a language model is never involved (ADR-0003). The rules are data
(`rulepacks/ai-act/<version>/pack.yaml`), each naming the provision it comes from and the
date it applies from.

Questions are asked in stages, in the order of the Regulation (ADR-0035):

| Stage | Provisions | Outcome |
|---|---|---|
| Scope | Art. 2 and 3 | `out_of_scope` when an exclusion applies |
| Prohibited practices | Art. 5(1), points (a) to (h), with (ba) and (bb) | `prohibited` |
| High-risk | Art. 6(1) with Annex I; Art. 6(2) with each point of Annex III; Art. 6(3) | `high_risk` |
| Transparency | Art. 50(1) to (4) | `transparency` |
| Otherwise | | `minimal` |

- The tier is the most severe outcome among the rules that hold; the others stay in the
  result.
- **An unanswered question is never read as "no".** While a question that could lead to a
  more severe outcome is open, the tier is `undetermined`, and
  `arbiter systems questions KEY` lists what to answer. Details of an area are asked only
  once the area applies.
- **Article 6(3) derogation** (ADR-0036). Arbiter does not judge whether the derogation
  holds: the Regulation gives that assessment to the provider. A declaration records
  that the provider claims it (`high_risk.derogation_claimed`) and where its documented
  assessment is (`high_risk.derogation_assessment_ref`). A system that performs profiling
  of natural persons stays high-risk whatever is claimed.
- **Obligations** are listed with their provision, the role they are addressed to and
  the date they apply from. An obligation of the future is shown as readiness, not as
  something already due.

Application dates in the pack, from Article 113 as amended by Regulation (EU) 2026/1744:

| What | Applies from |
|---|---|
| Prohibited practices, AI literacy | 2 February 2025 |
| Prohibitions of Art. 5(1)(ba) and (bb) | 2 December 2026 |
| Transparency obligations (Art. 50) | 2 August 2026 |
| High-risk under Annex III | 2 December 2027 |
| High-risk under Annex I | 2 August 2028 |

### What the pack does not cover

Obligations of providers, importers and distributors beyond Article 50; general-purpose
AI models (Chapter V); the exclusions of Article 2(4) and 2(12); Commission guidelines,
harmonised standards and national law. A system for which these matter needs more than
this tool.

## Review by a person

Every classification starts as a proposal (ADR-0037).

```bash
arbiter systems review cv-screening --confirm --reviewer "Ada Lovelace"
arbiter systems review loan-pre-screening --override high_risk \
  --reason "The provider's assessment does not cover our use." --reviewer "Ada Lovelace"
```

- Confirming keeps the indicative tier. Overriding sets another and needs a reason. An
  `undetermined` classification cannot be confirmed.
- The engine's result is never altered: the review is a separate record, and both are in
  the audit log. The reviewer appears there by identifier, not by name.
- When the facts or the rule pack change, a new classification supersedes the old one
  and needs its own review.

Over HTTP the review is recorded under the principal of the API key.

## Scanning and findings

`arbiter scan` computes, for each declared system, facts from its declaration, its
current classification and the metadata of its gateway traffic in the last 30 days, and
evaluates the scan rules (`rulepacks/scan/<version>/pack.yaml`). No rule sees prompt or
completion text: none is stored.

| Rule | Reports |
|---|---|
| `SCAN-SYSTEM-NOT-CLASSIFIED` | A declared system with no classification |
| `SCAN-CLASSIFICATION-UNDETERMINED` | Facts are missing that could change the classification |
| `SCAN-CLASSIFICATION-NOT-REVIEWED` | A classification nobody has confirmed or overridden |
| `SCAN-PROHIBITED-PRACTICE` | A system classified as a prohibited practice that is not retired |
| `SCAN-DEROGATION-WITHOUT-ASSESSMENT` | The Art. 6(3) derogation claimed with no reference to the provider's assessment |
| `SCAN-TRANSPARENCY-NOTICE-NOT-ATTESTED` | A transparency obligation of the deployer with no notice attested |
| `SCAN-HUMAN-OVERSIGHT-NOT-ATTESTED` | A high-risk system with no human oversight attested |
| `SCAN-UNDECLARED-MODEL-IN-TRAFFIC` | Traffic reached a model the declaration does not list |
| `SCAN-PERSONAL-DATA-NOT-DECLARED` | Personal data detected in prompts of a system not declared as processing any |
| `SCAN-RETIRED-SYSTEM-IN-USE` | A retired system that still sends traffic |
| `SCAN-SYSTEM-WITHOUT-OWNER` | No owner named |
| `SCAN-ROLE-NOT-COVERED` | A role whose obligations this version does not evaluate |
| `SCAN-UNDECLARED-SYSTEM-CANDIDATE` | A project, or a group of an imported source, makes requests that no declared system accounts for. One finding per candidate (see below) |
| `SCAN-UNATTRIBUTED-TRAFFIC` | Requests tied to no declared system that nothing groups into a candidate |
| `SCAN-MCP-SERVER-LEGACY-ONLY` | An MCP server of the catalogue offers no protocol revision the proxy speaks |
| `SCAN-AGENT-NOT-GOVERNABLE` | An A2A agent offers no binding the proxy speaks on the host of its card |
| `SCAN-AGENT-CARD-INVALID` | The card of an agent names a trusted key and its signature does not verify |
| `SCAN-AGENT-CARD-NOT-VERIFIED` | The card of an agent is unsigned, or signed with a key that is not trusted |
| `SCAN-TARGET-WITHOUT-SYSTEM` | An MCP server or an agent belongs to no declared AI system |
| `SCAN-CALLS-NOT-GRANTED` | Callers tried to use a server or an agent that no grant allows them |
| `SCAN-UNKNOWN-TARGET-IN-TRAFFIC` | Calls named a server or an agent that no catalogue holds. One finding per name |

The last seven are about tools and agents (Phase 5): they read the MCP catalogue and the
A2A registry of the gateway, and the calls recorded by the two proxies, never their
content. A finding about a server or an agent is attached to the AI system it belongs
to. See [the gateway](gateway.md) for the catalogues and the proxies.

Controls the organisation attests in a declaration, read by these rules:
`controls.transparency_notice`, `controls.human_oversight_assigned`,
`data.personal_data_processed`. A control that is not declared counts as not attested.

A finding about an obligation that does not apply yet has a lower severity until it
does: it is a matter of readiness.

### Systems nobody declared

Traffic that belongs to no declared system is grouped into candidates (ADR-0042): by
the **project** of the API key for requests through Arbiter's gateway, by the **group**
the source names (in LiteLLM, the team alias) for imported records. The scan reports one
finding per candidate, with the number of requests, the models used and the categories of
personal data detected.

```bash
arbiter systems discover                    # the candidates of the last 30 days
arbiter systems discover --draft > drafts.yaml
# complete name, purpose, roles and facts in drafts.yaml, then:
arbiter systems apply -f drafts.yaml
```

- A candidate is a proposal. Nothing is declared until a person completes a
  declaration, and a draft answers no question of the rule packs: the system it
  declares is `undetermined` until its facts are given.
- A draft of a project names it (`project_id`). Once the system is declared, the
  unattributed requests of that project count as the system's own in scans and reports,
  and the candidate closes at the next scan.
- For the gateway to apply the tier of the system (the policy on prohibited practices,
  the routing constraints), its keys must be tied to it:
  `arbiter keys create --name NAME --system KEY`.
- For imported records, add a mapping under `ingest.mappings` so that later imports are
  attributed to the system.
- A scan pack from before `2026.10.1` keeps the earlier behaviour: all such traffic in
  one finding.

Over HTTP: `GET /api/v1/candidates` lists the candidates with a draft declaration for
each; it needs the auditor or the admin role.

### Lifecycle

```text
open -> confirmed -> mitigated
open -> false_positive          (reason required)
open, confirmed -> accepted     (reason and expiry date required)
```

```bash
arbiter findings list
arbiter findings show 1a2b3c4d
arbiter findings review 1a2b3c4d --to confirmed --reviewer "Ada Lovelace"
arbiter findings review 1a2b3c4d --to false_positive --reviewer "Ada Lovelace" \
  --reason "Ownership is tracked in the CMDB." --suppress system
```

- A repeated detection updates the finding instead of creating another.
- The scanner makes three moves on its own, each recorded: a mitigated finding detected
  again is reopened; an accepted risk whose expiry has passed is reopened; an active
  finding that is no longer detected is marked as mitigated.
- A suppression stops a rule for one finding, one system or everywhere, with a reason
  and an optional expiry.
- The digest shows, per rule, how many findings reviewers confirmed and how many they
  rejected: a rule that is often rejected needs fixing.

## The digest

```bash
arbiter digest run                                   # Markdown, English, standard output
arbiter digest run --locale all --format both -o out/   # four files
```

Inventory by indicative tier, active findings by severity with provisions and dates,
reviewer feedback per rule, gateway traffic of the period with estimated cost, and the
head of the audit chain. Printing the head puts a copy of it outside the database, which
is what makes a later rewrite of the log detectable (see [the audit log](audit.md)).

Scheduling is external: run the command from cron or a container job.

### Sending it

`arbiter digest run --send` sends the digest to the configured recipients, each in their
language, as one message per language with a plain text part (the Markdown) and an HTML
part.

```yaml
plugins:
  notifier: smtp                  # default: file
notifications:
  sender: arbiter@example.org
  recipients:
    - { address: ada@example.org, locale: it }
    - { address: grace@example.org }          # locale: en
  settings:                       # of the notifier named above
    host: mail.example.org
    port: 587
    security: starttls            # starttls, tls (port 465) or none
    username: arbiter
    password: secret://smtp-password   # ARBITER_SECRET_SMTP_PASSWORD, never the value
```

| Notifier | Does | Settings |
|---|---|---|
| `file` (default) | Writes each message as an `.eml` file. Nothing leaves the machine | `directory` (default `.arbiter/outbox`) |
| `smtp` | Sends through an SMTP server, with the standard library | `host`, `port`, `security`, `username`, `password`, `timeout_seconds` |

- The default sends nothing: a digest holds the names of systems and their findings,
  and it goes to a mail server only when an operator names one.
- Credentials are refused on a connection without encryption (`security: none`).
- The configuration is checked before the digest is built. The database holds no open
  transaction while the mail server is being talked to.
- Each delivery is one audit entry, `digest.sent` or `digest.send_failed`, with the
  number of messages and of recipients and never the addresses. When a message fails,
  the command stops there and exits with an error; the server's own words are dropped
  and only the kind of failure is kept.
- With `--send` the digest is printed only when `-o DIR` is given.

Over HTTP: `POST /api/v1/digests/deliveries`, for the admin role. It answers 409 when
the configuration cannot deliver, and 502 when a message could not be delivered.

The `smtp` notifier delivers to the mail catcher of the Compose stack in the container
check, over plain SMTP (ADR-0045). STARTTLS, TLS and authentication are covered by tests
that replace the SMTP client, not by a server.

## Reports

Two documents meant for people outside the tool, in Markdown or HTML, in English or
Italian. They read what is recorded and change nothing.

```bash
arbiter report system cv-screening                      # Markdown, English, standard output
arbiter report system cv-screening --locale all --format both -o out/
arbiter report audit                                    # the last 30 days
arbiter report audit --since 2026-09-01 --until 2026-09-30 --format html -o out/
```

| Report | Holds |
|---|---|
| System | The declaration with its AI Act roles; the indicative tier, its review, and the tier the rules computed when a reviewer set another; what follows from the classification, each with its provision, the role it is addressed to and the date it applies from; the questions still open; earlier classifications; every finding with its status; traffic of the last 30 days |
| Audit | Whether the hash chain verifies, recomputed from its first entry whatever the period; the head of the chain; the entries of the period counted by action, and listed (the first 500: the export holds them all) |

- The system report says "indicative" and carries the note on the pending review of the
  rule pack, like every other output.
- The reviewer's reason is printed; the reviewer is not named.
- The audit report lists entries by identifier, as the log stores them. Dates of
  `--since` and `--until` are UTC days, both included.
- A chain that verifies is internally consistent, not proven untouched: see
  [the audit log](audit.md).
- PDF is an optional extra (ADR-0057): `--format pdf -o DIR` renders the HTML report
  and converts it, fetching nothing. It needs the extra `pdf` (from a clone:
  `uv sync --extra pdf`) and the Pango library of the operating system (on Debian or
  Ubuntu: `apt install libpango-1.0-0 libpangoft2-1.0-0`). The container image does
  not include it, and the HTTP API serves Markdown and HTML only. Without the extra,
  the HTML reports and the HTML digest still carry a print style sheet: open the file
  in a browser and print it. The digest has no PDF output.

Over HTTP: `GET /api/v1/systems/{key}/report` and `GET /api/v1/audit/report`, with
`format`, `locale` and, for the audit report, `days`. Both need the auditor or the admin
role.

## Importing the records of another gateway

Traffic that did not go through Arbiter can still be counted and scanned (ADR-0019).

```bash
arbiter ingest examples/interactions.jsonl                    # Arbiter's own format
arbiter ingest examples/litellm-logs.jsonl --source litellm   # LiteLLM standard logging payload
```

- One JSON record per line. Prompt and completion text is **dropped on the way in**: of
  a LiteLLM record, the importer keeps the metadata and the categories of personal data
  its messages contain, never the messages.
- Safe to repeat: a record already imported, recognised by its source and its
  identifier there, is skipped.
- A record that cannot be read is counted and its line number printed, without its
  content; `--strict` stops at the first one.
- Imported records enter the usage totals and the scan like the gateway's own, and the
  import is one entry of the audit log.

A record is attributed to a declared system in one of three ways: the `system` field of
the canonical format; in LiteLLM, the request tag `arbiter:system=<key>`; or a mapping in
the configuration, matched on labels of the source (LiteLLM records carry `key_alias` and
`team_alias`):

```yaml
ingest:
  mappings:
    - source: litellm
      labels: { team_alias: hr }
      system: cv-screening
```

A record that is attributed to no system keeps its `group`: the team or the application
it came from at the source, never a person (of a LiteLLM record, the team alias and not
the alias of the key). That is what lets the scan name a candidate system for it.

The LiteLLM mapping was written from the specification LiteLLM documents for its
standard logging payload. It has not been run against the output of a live LiteLLM.

## A guided demonstration

One command shows the gateway and the toolkit at work, in about a minute, on invented
data:

```bash
arbiter init
arbiter demo tour                 # or: --locale it
arbiter demo tour --case consulting   # an IT consulting firm with its own regulation
```

The second one, and how to give it live, is described in [Giving a demonstration](demo.md).

| Step | What it shows |
|---|---|
| The inventory | The scenarios below are loaded into the tenant `demo`, classified and scanned |
| Personal data is masked | A request with an e-mail address goes through the gateway; the address is masked before the model sees the prompt |
| A prohibited practice gets no model | The same request, with the key of a system classified as a prohibited practice, is denied, and the answer names the rule |
| Tools | An MCP server is registered and a grant names one of its tools: calling that one goes through, calling another is denied |
| Agents | An agent whose card a trusted key signed is called; then the card is changed, the signature no longer verifies, and the call is denied |
| Declared against observed | A scan compares the declarations with what just happened |
| Everything is on record | The audit chain is recomputed over every entry |

- **Everything runs in the process of the command.** The model is the mock provider;
  the MCP server and the agent are stand-ins (`adapters/mock/tools.py`); the key that
  signs the agent's card is made for the run and never written. No network, no real
  model (ADR-0033).
- It needs the `gateway`, `mcp` and `a2a` extras (`uv sync --all-extras`). Without `a2a`
  the step on agents is skipped and said to be.
- It touches the tenant `demo` only, uses two systems of its own
  (`tour-office-assistant`, `tour-mood-monitor`) so that its traffic lands on no
  scenario, and can be repeated.
- It exits with an error when a step does not go as expected.
- Afterwards, look at what it left: `arbiter findings list --tenant demo`,
  `arbiter report audit --tenant demo`, `arbiter digest run --tenant demo`.

## Simulation scenarios

To see the toolkit at work without declaring anything of your own, load a scenario
(ADR-0043). Every system and every request of a scenario is invented.

```bash
arbiter demo list
arbiter demo run shadow-ai            # or: arbiter demo run --all
arbiter findings list --tenant demo
arbiter systems discover --tenant demo
arbiter digest run --tenant demo --locale it
```

| Scenario | Shows |
|---|---|
| `inventory-in-order` | Three systems of three tiers, each owned and reviewed, with traffic that matches the declarations. Expected: no findings |
| `first-inventory` | A proposal that would be a prohibited practice, a derogation claimed without its assessment, a system with questions open; no owner, no review. Expected: what each is missing |
| `shadow-ai` | A model in traffic that the declaration does not list, personal data where none was declared, a retired system still in use, and two teams with no declared system. Expected: each contradiction, and both teams named as candidates |

- A scenario is one YAML file shipped with the package
  (`src/ai_arbiter/scenarios/`): the declarations, the reviews to record, traffic as
  counts per system (never text), and the tier and the findings expected of each
  system. It holds no code.
- `arbiter demo run` loads it into the tenant `demo` and no other, classifies, scans,
  and prints what was found next to what the scenario expects. It exits with an error
  when they differ: then a rule or the scenario needs fixing. Running it again adds
  nothing.
- Simulated requests are stored with the source `simulation`. They are not in the
  usage totals.
- The test suite runs every scenario: a change to a rule that alters an outcome fails
  a test.
- "No findings" means these rules found nothing. It does not mean that the systems of
  a scenario satisfy the Regulation.

## The gateway and the inventory

When both halves run in one process (`arbiter serve`):

- a request made with a key tied to a system classified as a **prohibited practice** is
  denied by the default policy (`POL-SYSTEM-PROHIBITED`);
- `router.constraints` limits where the requests of a risk tier may go:

  ```yaml
  router:
    constraints:
      high_risk:
        allowed_regions: [westeurope, italynorth]
        # allowed_deployments: [azure-gpt4o-we]
  ```

  A deployment that is excluded appears in the audited routing decision with the reason.

Both use the effective tier: the reviewer's, when a person overrode the engine.

## Events and the worker

Declaring or changing a system publishes an event. `arbiter worker` delivers pending
events and classifies the systems concerned; `arbiter worker --once` delivers what is
pending and exits. `arbiter systems apply` already classifies what it declares, so the
worker matters when systems are declared through the API without classification, and
for the consumers that later versions add.

## Retention

```bash
arbiter retention purge --dry-run
arbiter retention purge
```

| Data | Default | Configurable |
|---|---|---|
| Interactions | 13 months | `retention.interaction_months`; per tenant; never less than six months for a system whose effective tier is high-risk |
| Outbox events | 7 days after dispatch | `retention.outbox_days` |
| Audit entries, usage totals | Kept | No |
| Classifications, findings, reviews | Kept | No |

The six-month floor follows Article 26(6). National law may require longer periods: that
is for the operator to configure. The purge writes one audit entry with counts and
cut-off dates (ADR-0038).

## Limits of this release

- The classification is only as good as the declared facts. Nothing checks that a
  declaration is true; the scanner checks a few things traffic can contradict.
- The rule pack summarises provisions as questions. The summaries are not the legal
  text, and the pack's review against EUR-Lex is pending.
- Deployer obligations only. A provider gets a tier and no list of its obligations
  beyond Article 50.
- Twenty-one scan rules. The local agent is planned for v0.1.x (ADR-0009).
- A discovered candidate is as fine as its project: a project that runs several systems
  shows as one. A candidate from imported records stays until those records leave the
  30-day window, because imported records are attributed at import and not afterwards.
- Reports are Markdown and HTML; PDF needs an optional extra and a system library, and
  exists on the command line only.
- Personal data in traffic is detected by format only (see [the gateway](gateway.md)).
