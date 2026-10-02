# Phase 4: preparation

- **Status**: preparation only. No rule and no code has been written. Waits for the
  decisions of the project owner listed in section 3
- **Date**: 2026-10-02
- **Inputs**: ADR-0003, ADR-0007, ADR-0009, ADR-0012, ADR-0022; the Phase 0 analysis,
  whose dates came from secondary sources; open question Q3
- **Expected output from the project owner**: decisions P4-1 to P4-5

> Arbiter is a support tool. It does not provide legal advice. This document reports what
> the legal texts say; it does not interpret them for any particular system.

## 1. Verification of the AI Act text and calendar

### Sources and method

| Document | Identifier | Retrieved from | SHA-256 of the file retrieved |
|---|---|---|---|
| Regulation (EU) 2024/1689, Official Journal L of 12.7.2024 | CELEX 32024R1689 | `https://publications.europa.eu/resource/celex/32024R1689` | `8f0b656302f9864cc87e040c371f209a9d65ae1a6cecc25ca5eb737e872d721a` |
| Regulation (EU) 2026/1744 of 8 July 2026 (Digital Omnibus on AI), Official Journal L of 24.7.2026 | CELEX 32026R1744 | `https://publications.europa.eu/resource/celex/32026R1744` | `9d754652b867722807e4219c85912ce354233e58a1b4eb8c7752b4d1922993db` |
| Consolidated text of Regulation (EU) 2024/1689 as of 27.07.2026 | CELEX 02024R1689-20260727 | `https://publications.europa.eu/resource/celex/02024R1689-20260727` | `5e7719f77e8a606b257dc25958ee3222c4383300a5a34270a5b850a2ce8b8715` |

All three were retrieved on 2026-10-02, in English, from the Publications Office of the
European Union (CELLAR), the repository that EUR-Lex itself serves its documents from,
addressed by CELEX number.

**Limit of the method.** The working rule of the project names EUR-Lex. The EUR-Lex
website answers automated requests with a verification page and no content, from the
Codespace and from the fetch tool alike, so nothing was read on `eur-lex.europa.eu`
itself. The documents are the same Official Journal texts under the same CELEX numbers,
but the owner has not yet confirmed that this source satisfies the rule: see decision
P4-1.

The Official Journal texts are the authentic ones. The consolidated text says of itself
that it "is meant purely as a documentation tool and has no legal effect"; it was used to
read the amended articles in one place and checked against the amending act.

### What was checked

- No corrigendum to either regulation is published under the usual CELEX suffix
  (`R(01)`): both requests return "not found".
- A web search for later proposals or acts changing the application dates found none.
  This is a search, not proof: the legislative observatories were not consulted.
- National law, Commission guidelines and harmonised standards were not read.

### Application calendar, as amended

From Article 113 of Regulation (EU) 2024/1689 as amended by Article 1, point 40, of
Regulation (EU) 2026/1744, and from Article 111 as amended by point 39.

| Date | What applies | Provision |
|---|---|---|
| 1 August 2024 | Entry into force | Art. 113, first paragraph (twentieth day after publication on 12.7.2024) |
| 2 February 2025 | Chapters I and II: general provisions, AI literacy (Art. 4), prohibited practices (Art. 5) | Art. 113(a) |
| 2 August 2025 | Chapter III Section 4 (notified bodies), Chapter V (general-purpose AI models), Chapter VII (governance), Chapter XII (penalties) and Art. 78, except Art. 101 | Art. 113(b), unchanged |
| 27 July 2026 | Regulation (EU) 2026/1744 enters into force; Articles 102 to 110 apply | Art. 4 of 2026/1744 (third day after publication on 24.7.2026); Art. 113(d) |
| 2 August 2026 | General date of application: everything not listed otherwise, including the transparency obligations of Art. 50 | Art. 113, second paragraph, unchanged |
| 2 December 2026 | The two prohibitions added to Art. 5(1), points (ba) and (bb), with Art. 5(1a) and (1b). End of the period for providers of generative systems placed on the market before 2 August 2026 to comply with Art. 50(2) | Art. 113(a); Art. 111(4) |
| 2 August 2027 | Providers of general-purpose AI models placed on the market before 2 August 2025 must comply. National AI regulatory sandboxes operational. Delegated acts under Art. 2(13) due | Art. 111(3), unchanged; Art. 57(1); Art. 2(13) |
| 2 December 2027 | Chapter III Sections 1, 2 and 3 (except Art. 6(5)) for systems that are high-risk under Art. 6(2) and Annex III | Art. 113(c)(i) |
| 2 August 2028 | The same for systems that are high-risk under Art. 6(1) and Annex I | Art. 113(c)(ii) |
| 2 August 2030 | High-risk systems intended to be used by public authorities, already on the market | Art. 111(2) |
| 31 December 2030 | Components of the large-scale IT systems of Annex X placed on the market before 2 August 2027 | Art. 111(1), unchanged |

### The Phase 0 analysis against the primary text

| Statement in the Phase 0 analysis (secondary sources) | Verified |
|---|---|
| The amending act is Regulation (EU) 2026/1744 | Confirmed |
| Adopted by the Council on 29 June 2026, in force from 27 July 2026 | Confirmed: Council decision of 29 June 2026 (footnote 4), act of 8 July 2026, published 24 July, in force on the third day |
| High-risk obligations for Annex III moved to 2 December 2027, for Annex I to 2 August 2028 | Confirmed |
| Art. 50 not postponed; transition to 2 December 2026 for Art. 50(2) | Confirmed. The transition covers only systems placed on the market before 2 August 2026 |
| New prohibitions from 2 December 2026 | Confirmed: Art. 5(1)(ba) and (bb) |
| Art. 4 softened from "ensure" to "support the development" | Confirmed, with the sentence that it "does not require providers or deployers to guarantee any specific level of AI literacy of any individual" |
| Legal basis for processing special categories of data for bias detection extended | Confirmed: new Art. 4a |
| Exclusive competence of the AI Office over systems built on a general-purpose model by the same provider | Confirmed, with exceptions: Art. 75(1) |
| General-purpose models placed on the market before 2 August 2025: 2 August 2027 | Confirmed, unchanged |

Not in the Phase 0 analysis, and relevant to the rule pack:

- **Art. 6(1a) to (1c)**, new: systems used solely for non-safety aspects (assistance,
  optimisation, efficiency, convenience, quality control) are not safety components,
  unless their failure would endanger health and safety.
- **Art. 111(2)**: the cut-off for systems already on the market is now "the date of
  application of Chapter III", not 2 August 2026.
- **Annex I**: the machinery regulation moves from Section A to Section B.
- **Annex III is unchanged**: eight areas, no amendment marker in the consolidated text.
- **Art. 6(3) and (4) are unchanged**: the derogation, the rule that a system performing
  profiling of natural persons is always high-risk, and the provider's duty to document
  the assessment and register (Art. 49(2)).
- **Art. 26(6) and Art. 19(1) are unchanged**: logs kept for "at least six months".
- **Art. 27(4)** is amended (relation between the fundamental rights impact assessment
  and the data protection impact assessment). Its new text was not analysed here.
- Small mid-cap enterprises (SMCs) get the simplifications that SMEs had.

## 2. Two findings outside the legal text

### GitHub Models is retired

The owner asked to evaluate GitHub Models as a real provider for demos through the
OpenAI-compatible adapter. The official documentation
(<https://docs.github.com/en/github-models>) states: "As of July 30, 2026, GitHub Models
has been fully retired. The playground, model catalog, inference API, and bring your own
key (BYOK) are no longer available to any customer." It points to Azure AI Foundry and
GitHub Copilot instead.

Checked on 2026-10-02: `https://models.github.ai/inference/chat/completions` answers
HTTP 200 with the plain text `OK`, with or without a token, and no completion. There is
nothing to integrate. The alternatives are in decision P4-6.

### CodeQL alerts cannot be read from the Codespace

`gh api repos/ViciusLio/ai-arbiter/code-scanning/alerts` returns 403 ("Resource not
accessible by integration"). The CodeQL workflow itself passes on every commit. The
alert list has to be read by the owner, in the Security tab. The same call shows that
Dependabot alerts are disabled for the repository; enabling them is a repository setting
and is the owner's choice.

## 3. Decisions to take before Phase 4 starts

Each has an option table on the seven criteria and a recommendation. The numbering
(P4-n) is what the owner answers with.

### P4-1: which source counts as "the official text"

| Criterion | 1. Publications Office (CELLAR) by CELEX number | 2. The owner downloads the texts from EUR-Lex into the repository | 3. CELLAR for the work, and the owner spot-checks listed articles on EUR-Lex |
|---|---|---|---|
| Complexity | Lowest: already done | A manual step at every rule pack release | Low |
| Azure cost | None | None | None |
| Scalability | Repeatable by script at every release | Depends on a person | Repeatable, with a short manual step |
| Security | Official EU domain; checksum recorded | Same documents | Same |
| Compliance / privacy | Same documents as EUR-Lex, but not the site the rule names | Matches the rule to the letter | Matches the rule, with evidence of a human check |
| Maintainability | Good | Poor | Good |
| Lock-in | None | None | None |

Recommendation: **3**. The rule pack records CELEX numbers, retrieval date and checksums;
the owner confirms on EUR-Lex the articles the pack quotes (the list is short: Art. 2, 3,
4, 5, 6, 26, 27, 50, 111, 113 and Annex III) and the pack is marked
`verified_against: primary` only after that.

### P4-2: the facts the classifier asks for

| Criterion | 1. One fact per legal provision (about 60, flat) | 2. A few coarse facts (about 15) | 3. Staged: coarse areas first, then the detailed facts of the areas that apply |
|---|---|---|---|
| Complexity | Medium: long but simple | Low | Medium |
| Azure cost | None | None | None |
| Scalability | New provisions add facts | Coarse facts hide distinctions the law makes | New areas add a stage |
| Security | Not affected | Not affected | Not affected |
| Compliance / privacy | Traceable to the article, tedious to fill: unanswered facts likely | Easy to fill, but a rule cannot cite the exact point of Annex III | Traceable to the article; unanswered facts are reported as missing, and the outcome is `undetermined` rather than a guess |
| Maintainability | One long list | Short, and wrong | Two short lists per area |
| Lock-in | None | None | None |

Recommendation: **3**. Stages follow the order of the Regulation: scope and exclusions
(Art. 2), prohibited practices (Art. 5), high-risk (Art. 6 with Annex I and Annex III),
transparency (Art. 50). Every fact names the provision it comes from. A fact left
unanswered never counts as "no".

### P4-3: who may claim the derogation of Art. 6(3)

Art. 6(3) lets an Annex III system be treated as not high-risk under four conditions,
never when it performs profiling. Art. 6(4) puts the assessment on the **provider**.
Arbiter covers the deployer first (ADR-0007).

| Criterion | 1. A deployer records that the provider claims the derogation, with a reference to the provider's assessment | 2. No derogation for deployers: an Annex III system is always high-risk in the tool | 3. The tool evaluates the four conditions from facts the deployer declares |
|---|---|---|---|
| Complexity | Low | Lowest | Medium |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | Not affected |
| Security | Not affected | Not affected | Not affected |
| Compliance / privacy | Follows Art. 6(4): the provider assesses, the deployer keeps evidence. Without the reference, a finding is raised | Over-classifies: safe, but reports obligations that may not apply | The tool would decide what the law gives the provider to assess |
| Maintainability | Simple | Simplest | Rules that mirror a legal judgement |
| Lock-in | None | None | None |

Recommendation: **1**, with the profiling rule enforced by the pack: a system declared
as profiling natural persons stays high-risk whatever is claimed. When the organisation
is itself the provider (ADR-0022 allows both roles), the four conditions are recorded as
its own declared assessment, not computed.

### P4-4: review and override of a classification by a person

| Criterion | 1. Automatic and final: a person can only change the declared facts | 2. Automatic, and a person may override the result with a reason | 3. Every result is a proposal until a named person confirms it; that person may confirm or override with a reason |
|---|---|---|---|
| Complexity | Lowest | Low | Medium: a status and a review step |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | A review queue to work through |
| Security | Not affected | The override is audited | Confirmation and override are audited |
| Compliance / privacy | Nobody is accountable for the result; no way to record a reasoned disagreement | The engine's result and the person's are both kept | Matches "support tool, not legal advice": nothing is presented as settled until a person took responsibility |
| Maintainability | Simple | Simple | A workflow to maintain, shared with findings |
| Lock-in | None | None | None |

Recommendation: **3**. Outputs show `indicative` until confirmed. The engine's result is
never altered: a confirmation or an override is a separate record with reviewer, reason
and date, and both are audit entries. The same workflow serves findings.

### P4-5: retention defaults

Verified in the text: deployers of high-risk systems keep automatically generated logs
"for a period appropriate to the intended purpose [...] of at least six months, unless
provided otherwise in applicable Union or national law, in particular in Union law on the
protection of personal data" (Art. 26(6)). Arbiter's interactions hold metadata only.

| Criterion | 1. The defaults of the data model, no floor by risk class, no purge yet | 2. The same defaults, a six-month floor for interactions of systems classified high-risk, and a purge command | 3. Keep everything; retention is documented and not enforced in v0.1 |
|---|---|---|---|
| Complexity | Low | Medium: a purge job and its tests | Lowest |
| Azure cost | Storage grows | Bounded storage | Storage grows without bound |
| Scalability | Tables grow | Tables bounded by the retention period | Tables grow |
| Security | More data kept than needed | Less data to lose | Most data to lose |
| Compliance / privacy | Minimisation promised and not delivered | Minimisation delivered; the floor is tied to a verified provision; the purge is audited | Hard to defend under the GDPR storage limitation principle |
| Maintainability | Nothing to run | One command, scheduled outside Arbiter | Nothing to run |
| Lock-in | None | None | None |

Recommendation: **2**. Defaults: interactions 13 months, never less than six months for a
system classified high-risk; outbox events 7 days after dispatch; audit entries and
roll-ups kept. `arbiter retention purge` deletes what is past its period and writes one
audit entry with counts, never content. A tenant can lengthen a period, and shorten it
down to the floor.

### P4-6: a real provider for demos and manual checks

GitHub Models no longer exists (section 2). The constraints the owner set still hold:
no automated test or CI job depends on a real model, the key is a `secret://` reference,
prompts are synthetic, and the documentation says where data goes.

| Criterion | 1. Ollama in a container, started for the demo and removed after | 2. A hosted OpenAI-compatible service with a free tier, with a key from the owner | 3. Azure AI Foundry, in Phase 6 | 4. No real provider: demos use the mock |
|---|---|---|---|---|
| Complexity | Low: checked on 2026-10-02 | Low, after reading that service's terms | Part of the Azure phase | None |
| Azure cost | None | None | Pay per use | None |
| Scalability | Tiny models, slow on two cores | Real models | Real models | Not applicable |
| Security | Nothing leaves the Codespace | A credential to handle | Managed identity later | Nothing |
| Compliance / privacy | No data leaves | Prompts go to a third party, to be stated in the documentation | Prompts go to Azure, region chosen by the owner | Nothing |
| Maintainability | 9.3 GB image to pull each time, about 10 GB of the Codespace disk while it runs | Depends on the free tier lasting | The path the brief asks for | Nothing |
| Lock-in | None | Low | Azure, already the target (ADR-0008) | None |

Recommendation: **1 now and 3 in Phase 6**. Option 2 only if the owner wants a hosted
demo before Phase 6: the service is then named by the owner and its documentation read
before anything is configured. No such service was evaluated here.

## 4. Proposed order of work for Phase 4

After the decisions, and with one ADR per decision recorded first:

1. Inventory: AI systems declared through YAML, API and CLI, with their AI Act roles;
   the `SystemDirectory` port; the foreign key from API keys.
2. The AI Act rule pack, written from the texts of section 1, and the classifier.
3. Review workflow (P4-4), shared by classifications and findings.
4. Scanner: a first set of rules over the inventory and the interaction metadata.
5. Findings: model, lifecycle, suppressions.
6. Daily digest in Markdown and HTML, in English and Italian.
7. The outbox dispatcher (`arbiter worker`).
8. Retention (P4-5).
9. Then the first deferrable item: routing constraints by risk class.

---

*Arbiter is a support tool and does not provide legal advice.*
