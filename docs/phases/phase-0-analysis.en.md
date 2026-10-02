# Phase 0: Requirements analysis and proposed MVP scope (English summary)

This is a summary, in English, of [phase-0-analysis.md](phase-0-analysis.md), which is
kept in Italian as a historical document. It adds nothing and decides nothing: where the
two differ, the Italian text and the decision records are the reference. The initial
requirements are in [PROJECT_BRIEF.md](../PROJECT_BRIEF.md), also in Italian.

- **Status**: closed on 2026-10-02. Decisions D1 to D7 are recorded in
  [ADR-0002 to ADR-0008](../adr/README.md); the v0.1 scope is in
  [ADR-0009](../adr/0009-v0-1-scope.md)
- No code was written in this phase

## The argument

The brief describes fifteen modules across two products. Built to the same depth, they
would make a project that is wide and shallow. Three observations shape the proposal.

1. **A gateway alone is not distinctive.** LiteLLM, Kong AI Gateway, Portkey and
   agentgateway already route models, and some govern MCP and A2A. What none of them does
   well is link real traffic to an inventory of AI systems classified under the AI Act,
   with evidence that can be checked. That link is where Arbiter is worth building.
2. **The legal calendar changed in July 2026** with the Digital Omnibus on AI: the
   high-risk obligations moved to December 2027 and later, while Article 50 applies
   since August 2026. The first version should centre on what applies today.
3. **The protocols changed too.** A2A reached 1.0 and MCP published its largest
   revision. Arbiter should govern them through the official SDKs, not implement them
   again.

The proposal: v0.1 is one complete vertical slice, from a request through policy,
routing, metering and audit to inventory, classification, findings and the digest. A2A
and MCP, Azure, and packaging follow as v0.2, v0.3 and v1.0.

## What the analysis found

| Topic | Finding |
|---|---|
| AI Act calendar | Prohibited practices and AI literacy from 2 February 2025; Article 50 from 2 August 2026; high-risk under Annex III from 2 December 2027 and under Annex I from 2 August 2028. In Phase 0 these came from secondary sources; they were confirmed on the Official Journal text in [Phase 4](phase-4-preparation.md) |
| Consequences for the design | Every rule pack states its date and its legal basis, and every obligation the date it applies from. A finding cannot call something a violation before the obligation applies: until then it is about readiness |
| Protocols | A2A 1.0 with signed agent cards and an official Python SDK; MCP with a stateless core in its 2026 revision, while existing servers speak earlier ones. Both come from secondary sources and are checked again when Phase 5 opens |
| Landscape | Competing on the number of providers or on the speed of the data path is neither realistic nor useful |

## Ambiguities in the brief, and how they were settled

Twenty-one were listed. The ones that shaped the product:

| Requirement | Ambiguity | Settled as |
|---|---|---|
| Classifier | The brief does not name the role of the user, and obligations depend on the role | The inventory records the AI Act role; v0.1 evaluates the deployer |
| Classifier | A risk class depends on the intended purpose, which traffic does not show | Classification from declared attributes; traffic gives evidence and contradictions, not the class |
| Scanner | "Configurations, prompts, logs, datasets" is very wide | Configurations, inventory and traffic metadata; datasets are out of scope |
| Findings | "Feedback improves the rules" | Suppressions and precision per rule in the digest; no automatic tuning |
| Local agent | "Data flows to AI services" implies capturing network traffic | Static, read-only discovery of known configuration files; no capture |
| Audit | Append-only conflicts with erasure and retention | The log holds metadata and identifiers only; content is kept elsewhere, if at all |
| Audit | "Verifiable integrity" against whom | A hash chain, a verify command and an export; external anchoring later |
| Costs | Prices change and depend on region | A versioned, configurable price catalogue; costs are always estimates |
| Database | An offline CLI cannot require PostgreSQL | PostgreSQL and SQLite, with portable types and tests on both |
| Reports | PDF libraries need native dependencies | Markdown and HTML; PDF as an optional extra later (see ADR-0044) |
| "Production-ready" | Meaning for a v0.x project of one person | Production engineering practice and documented limits; not proven availability, penetration tests or service levels |

## Risks named

Scope too wide (answered by the vertical slice); rules overtaken by new acts (versioned
packs, check on the primary source at every release); a false sense of compliance (a
disclaimer on every output, "indicative" and "no findings", human review); the gateway as
a high-value target (secrets through adapters, keys stored as hashes, no prompt stored by
default); the quality of personal data detection, in Italian above all (pluggable
detectors, declared limits); the pace of A2A and MCP (pinned revisions, official SDKs);
added latency (measured); two databases (portable types); the local scan reading
sensitive files (read-only, explicit paths, consent).

## Simplifications proposed

Three provider adapters (Azure OpenAI, OpenAI-compatible, mock); an in-process event bus
with an outbox instead of a broker; tenants, teams, projects, API keys and three roles,
with Entra ID later; the digest as a command scheduled from outside; simulation scenarios
brought into v0.1; AKS and Terraform documented and not implemented; a scanner of ten to
fifteen high-precision rules.

## Decisions taken

| # | Question | Decision | Record |
|---|---|---|---|
| D1 | Positioning | Compliance first, with a lean gateway of its own | ADR-0002 |
| D2 | Classifier | Deterministic rules on declared attributes; a language model may suggest inputs, never decide | ADR-0003 |
| D3 | Language | English for code and documentation; user-facing outputs in English and Italian | ADR-0004 |
| D4 | Name | Brand Arbiter, distribution `ai-arbiter`, command `arbiter` | ADR-0005 |
| D5 | Web interface | None in v0.1 | ADR-0006 |
| D6 | Primary AI Act role | The deployer | ADR-0007 |
| D7 | Azure | No resource before Phase 6; subscription and budget still to be given | ADR-0008 |

Technical choices were left to Phase 1, each with its own option table and record:
[the decision index](../adr/README.md).

---

*Arbiter is a support tool and does not provide legal advice.*
