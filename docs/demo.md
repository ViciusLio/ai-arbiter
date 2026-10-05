# Giving a demonstration

Three ways, all on invented data, with no network, no cloud account and no real model.

> Arbiter is a support tool. It does not provide legal advice. Every system, firm and
> request in a demonstration is invented.

| What | Command | Takes |
|---|---|---|
| The product in general: gateway, tools, agents, scan, audit | `arbiter demo tour` | About a minute |
| A firm that approved one family of models, step by step in the terminal | `arbiter demo tour --case consulting` | A few seconds |
| The same run as a page to show: a deck with the steps and the figures | Add `--report out/demo.html` | A few seconds |
| The same firm, live: the service answers while people watch | The script below | Ten to fifteen minutes |

From a clone, put `uv run` in front of every `arbiter` command. Add `--locale it` to
have the texts, and the page, in Italian.

## The case: one approved model, many tools

Nordwind Consulting (invented) works by engagement: each client is a project of the
gateway. It approved one family of models, Claude, and nothing else. Its people reach
those models through several tools, and two of them could run on other engines. The
tools are declared in
[`scenarios/consulting/systems.yaml`](../src/ai_arbiter/scenarios/consulting/systems.yaml):

| System | What it is | Indicative tier |
|---|---|---|
| `claude-assistant` | The chat assistant every employee may use | Transparency obligations |
| `kiro-ide` | A coding environment, on a client's repository | Minimal |
| `github-copilot` | Code completion and chat in the editor | Minimal |
| `cv-screening` | Ranks applications for the recruiters | High-risk (Annex III, employment) |
| `meeting-mood-analyser` | Nobody uses it: a vendor proposed it | Prohibited practice (Article 5) |

The firm's internal AI regulation is a file,
[`scenarios/consulting/policy.yaml`](../src/ai_arbiter/scenarios/consulting/policy.yaml):
the default gateway policy plus the firm's own rules, with the list of approved models,
a budget per engagement and grants on tools.

| Internal rule | How it is enforced |
|---|---|
| Only approved models, whatever tool asks | `policy.allowed_models`, rule `POL-MODEL-NOT-ALLOWED` |
| Personal data of a client's customers never reaches a model | Redaction, rule `POL-PII-REDACT` |
| A credential of a client never leaves, not even masked | The firm's rule `IR-CREDENTIAL-IN-PROMPT` |
| A high-risk system gets no model before a person reviewed its classification | The firm's rule `IR-HIGH-RISK-NOT-REVIEWED` |
| Each engagement has a budget | A hard budget on the project, rule `POL-BUDGET-EXCEEDED` |
| On a client's repository, only the tools that were granted | Grants of the MCP catalogue, rule `MCP-CALL-NOT-GRANTED` |

What to say plainly while showing it:

- The product names are examples of how a firm labels its tools. Which engines a
  product offers, and whether it can be pointed at a gateway, is for each organisation
  to check with the vendor: nothing in Arbiter states it.
- Arbiter governs what passes through it. A request a tool sends straight to its
  vendor, or a service opened in a browser, is not seen: that is what reading the logs
  of the company network is for, which is planned and not built (ADR-0058).
- The internal rules are enforced on requests and written to the audit log. The scan
  reports the attempts through the rules shipped with Arbiter (a model the declaration
  does not list); it has no findings of the firm's own.

## In one command

```bash
arbiter init
arbiter demo tour --case consulting --report out/demo.html
```

Thirteen steps, each marked as expected or not: the inventory and its tiers, the
internal regulation, Kiro on the approved engine with personal data masked, the same
tool refused on another engine, Copilot allowed and refused in the same way, a refused
credential, the high-risk system before and after a review, the prohibited practice
refused even on an approved model, the budget of an engagement, the tools on the
client's repository, the use nobody declared, the findings, and the audit chain.

Everything lands in the tenant `demo-consulting`, apart from your own data and from the
other scenarios. The command can be repeated; on a second run the high-risk system is
already reviewed, and the step says so. A fresh directory shows the refusal again.

## The page

`--report FILE` writes the run as one self-contained HTML file: nothing is loaded from
anywhere, so it can be opened from disk, sent, or shown without a connection. It tells
the run as the story of one day at the firm, a deck read from left to right:

1. the premise, and the outcome of the run;
2. the rule of the firm in one sentence, and the approved models;
3. the people of the story: who they are and what they work with;
4. the declared tools with their indicative tiers;
5. one scene on each screen, with its time of day and its person: what the person does,
   what Arbiter does about it in plain words, and the rule that decided;
6. the day in one table: each tool, each engine it asked for, what went through and
   what was stopped;
7. what the head of the AI committee finds at the end of the day: the findings that
   matter, and a count of the smaller notes;
8. what stays on record, and what the story does not prove.

The people are invented, like the firm. Every outcome and every figure comes from the
run and from what the tenant holds: the story around them is fixed text. The page
contains no text of any request. It prints as a document, one section after the other.

## Live, step by step

Checked by hand on 2026-10-05 in a fresh workspace: the service started with the
settings below, a request for the approved model went through and one for another
engine was refused.

**Before people arrive.** In an empty directory:

```bash
arbiter init
arbiter demo tour --case consulting --locale it --report out/demo.html
```

**1. The page.** Open `out/demo.html` and go through it: it is the story in seven
screens.

**2. What the firm runs, and what the AI Act makes of it.**

```bash
arbiter systems list --tenant demo-consulting
arbiter systems show cv-screening --tenant demo-consulting --locale it
```

**3. Start the service with the firm's regulation.** `REPO` is the path of the clone;
[`examples/consulting/live.env`](../examples/consulting/live.env) sets the regulation,
the approved models and a stand-in that answers them.

```bash
REPO=/path/to/ai-arbiter source $REPO/examples/consulting/live.env
arbiter serve
```

**4. A consultant at work.** In a second terminal, in the same directory, create a key
for Kiro on the bank engagement. It is printed once.

```bash
arbiter keys create --tenant demo-consulting --name live --role developer \
  --team nordwind --project client-bank --system kiro-ide
```

Kiro on the approved engine, with an e-mail address in the question:

```bash
curl -i http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer arb_..." -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-5-5", "messages": [{"role": "user", "content": "Write to anna.bianchi@example.com about the release."}]}'
```

`X-Arbiter-Redacted: email` and `X-Arbiter-Policy: redact`: the address was replaced
before the prompt left. Then the same tool on another engine:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer arb_..." -H "Content-Type: application/json" \
  -H "Accept-Language: it" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'
```

The answer is a 403 that names the rule, `POL-MODEL-NOT-ALLOWED`, and the version of
the firm's pack. `curl http://127.0.0.1:8080/v1/models -H "Authorization: Bearer arb_..."`
lists what a tool may ask for: the two Claude models and nothing else.

**5. What the firm has to look at.**

```bash
arbiter scan --tenant demo-consulting
arbiter findings list --tenant demo-consulting --locale it
arbiter systems discover --tenant demo-consulting
```

The prohibited practice is on top; the attempts on other engines show as traffic to a
model the declaration does not list; the project `nordwind / lab` is a candidate system.

**6. Something to hand to people, money and proof.**

```bash
arbiter report system cv-screening --tenant demo-consulting --format html --locale it -o out
arbiter digest run --tenant demo-consulting --format html --locale it -o out
arbiter usage report --tenant demo-consulting --locale it
arbiter audit verify --tenant demo-consulting
```

**Afterwards.** Stop `arbiter serve` with Ctrl+C.

## What a demonstration does not prove

The model, the tool server and the agent are stand-ins. No real provider, no real MCP
server and no real agent is involved, no real product was connected to the gateway, and
nothing here says that an organisation meets its obligations: the classification is
indicative and the rule pack has not been reviewed by a person with legal training.
