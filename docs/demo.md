# Giving a demonstration

Two ways, both on invented data, with no network, no cloud account and no real model.

> Arbiter is a support tool. It does not provide legal advice. Every system, firm and
> request in a demonstration is invented.

| What | Command | Takes |
|---|---|---|
| The product in general: gateway, tools, agents, scan, audit | `arbiter demo tour` | About a minute |
| An IT consulting firm with its own internal regulation | `arbiter demo tour --case consulting` | A few seconds |
| The same firm, live: the service answers while people watch | The script below | Ten to fifteen minutes |

From a clone, put `uv run` in front of every `arbiter` command. Add `--locale it` to
have the texts in Italian.

## The case: an IT consulting firm

Nordwind Consulting (invented) works by engagement: each client is a project of the
gateway. Its people use four AI tools, declared in
[`scenarios/consulting/systems.yaml`](../src/ai_arbiter/scenarios/consulting/systems.yaml):

| System | Used by | Indicative tier |
|---|---|---|
| `code-assistant` | Consultants, on a client's repository | Minimal |
| `proposal-writer` | Sales, for offers | Transparency obligations |
| `cv-screening` | Recruiters | High-risk (Annex III, employment) |
| `meeting-mood-analyser` | Nobody: a vendor proposed it | Prohibited practice (Article 5) |

The firm has an internal AI regulation. In Arbiter it is a file,
[`scenarios/consulting/policy.yaml`](../src/ai_arbiter/scenarios/consulting/policy.yaml):
the default gateway policy plus the firm's own rules, with a list of approved models,
a budget per engagement and grants on tools.

| Internal rule | How it is enforced |
|---|---|
| Only approved models | `policy.allowed_models`, rule `POL-MODEL-NOT-ALLOWED` |
| Personal data of a client's customers never reaches a model | Redaction, rule `POL-PII-REDACT` |
| A credential of a client never leaves, not even masked | The firm's rule `IR-CREDENTIAL-IN-PROMPT` |
| A high-risk system gets no model before a person reviewed its classification | The firm's rule `IR-HIGH-RISK-NOT-REVIEWED` |
| Each engagement has a budget | A hard budget on the project, rule `POL-BUDGET-EXCEEDED` |
| On a client's repository, only the tools that were granted | Grants of the MCP catalogue, rule `MCP-CALL-NOT-GRANTED` |

What this does not show: the internal rules are enforced on requests and written to the
audit log, but the scan does not report on them as it does on the AI Act; the findings
of the scan come from the packs shipped with Arbiter.

## In one command

```bash
arbiter init
arbiter demo tour --case consulting
```

Eleven steps, each marked as expected or not: the inventory and its tiers, the internal
regulation, masking of personal data, a refused credential, a model that is not
approved, the high-risk system before and after a review, the prohibited practice, the
budget of an engagement, the tools on the client's repository, the use nobody declared,
and the audit chain. Everything lands in the tenant `demo-consulting`, apart from your
own data and from the other scenarios. The command can be repeated; on a second run the
high-risk system is already reviewed, and the step says so.

## Live, step by step

Checked by hand on 2026-10-05 in a fresh workspace, with the commands below.

**Before people arrive.** In an empty directory:

```bash
arbiter init
arbiter demo tour --case consulting --locale it
```

**1. What the firm runs, and what the AI Act makes of it.**

```bash
arbiter systems list --tenant demo-consulting
arbiter systems show cv-screening --tenant demo-consulting --locale it
```

Say: the tier is indicative until a person reviews it; every outcome names the
provision and the date behind it.

**2. Start the service with the firm's regulation.** `REPO` is the path of the clone.

```bash
export ARBITER_POLICY__PACK=$REPO/src/ai_arbiter/scenarios/consulting/policy.yaml
export ARBITER_POLICY__ALLOWED_MODELS='["mock-small"]'
arbiter serve
```

**3. A consultant at work.** In a second terminal, create a key for the coding
assistant on the bank engagement. It is printed once.

```bash
arbiter keys create --tenant demo-consulting --name live --role developer \
  --team nordwind --project client-bank --system code-assistant
```

Send a question that carries an e-mail address, and look at the response headers:

```bash
curl -i http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer arb_..." -H "Content-Type: application/json" \
  -d '{"model": "mock-small", "messages": [{"role": "user", "content": "Write to anna.bianchi@example.com about the release."}]}'
```

`X-Arbiter-Redacted: email` and `X-Arbiter-Policy: redact`: the address was replaced
before the prompt left. Then ask for a model the firm did not approve:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer arb_..." -H "Content-Type: application/json" \
  -H "Accept-Language: it" \
  -d '{"model": "mock-large", "messages": [{"role": "user", "content": "Hello"}]}'
```

The answer is a 403 that names the rule, `POL-MODEL-NOT-ALLOWED`, and the version of
the firm's pack.

**4. What the firm has to look at.**

```bash
arbiter findings list --tenant demo-consulting --locale it
arbiter systems discover --tenant demo-consulting
```

The prohibited practice is on top. The project `nordwind / lab` is named as a candidate
system: someone uses a model there and nobody declared it.

**5. Something to hand to people.** Open the two files in a browser.

```bash
arbiter report system cv-screening --tenant demo-consulting --format html --locale it -o out
arbiter digest run --tenant demo-consulting --format html --locale it -o out
```

**6. Money and proof.**

```bash
arbiter usage report --tenant demo-consulting --locale it
arbiter audit verify --tenant demo-consulting
```

Say: no prompt, no argument and no answer is stored; the audit log is a chain that can
be recomputed.

**Afterwards.** Stop `arbiter serve` with Ctrl+C.

## What a demonstration does not prove

The model, the tool server and the agent are stand-ins. No real provider, no real MCP
server and no real agent is involved, and nothing here says that an organisation meets
its obligations: the classification is indicative and the rule pack has not been
reviewed by a person with legal training.
