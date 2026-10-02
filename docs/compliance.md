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

```bash
arbiter init
arbiter systems apply -f examples/systems.yaml   # declare and classify seven invented systems
arbiter systems list
arbiter systems show cv-screening                # tier, obligations, provisions, dates
arbiter systems questions marketing-copy-generator   # what is still to answer
arbiter scan                                     # compare declarations, classification, traffic
arbiter findings list
arbiter digest run --locale it                   # or: --locale all --format both -o out/
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
| `SCAN-UNATTRIBUTED-TRAFFIC` | Requests made with API keys tied to no declared system |

Controls the organisation attests in a declaration, read by these rules:
`controls.transparency_notice`, `controls.human_oversight_assigned`,
`data.personal_data_processed`. A control that is not declared counts as not attested.

A finding about an obligation that does not apply yet has a lower severity until it
does: it is a matter of readiness.

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

Scheduling is external: run the command from cron or a container job. Delivery by e-mail
is planned for v0.1.x.

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
- Thirteen scan rules. Discovery of systems from traffic, importers for other gateways,
  reports, the local agent and e-mail delivery are planned for v0.1.x (ADR-0009).
- Personal data in traffic is detected by format only (see [the gateway](gateway.md)).
