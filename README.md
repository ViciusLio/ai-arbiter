# Arbiter

**Know which AI systems you run, and be able to show it.**

Arbiter is an open-source AI governance gateway and EU AI Act compliance toolkit. It
links what an organisation *declares* about its AI systems with what their traffic
*shows*, and reports what does not match.

[![CI](https://github.com/ViciusLio/ai-arbiter/actions/workflows/ci.yml/badge.svg)](https://github.com/ViciusLio/ai-arbiter/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Licence Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-green)
![Status alpha](https://img.shields.io/badge/status-alpha-orange)
[![PyPI](https://img.shields.io/pypi/v/ai-arbiter?include_prereleases&label=PyPI)](https://pypi.org/project/ai-arbiter/)

> **Alpha.** A first pre-release is on PyPI. It has never run in production, and it is
> not legal advice: every
> classification is indicative until a person reviews it, and the AI Act rule pack has
> not been reviewed by a person with legal training. Read
> [scope and limits](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/scope-and-limits.md) first.

| | English | Italiano |
|---|---|---|
| **See it at work**: a day at an invented firm, from a real run | [A day at Nordwind](https://viciuslio.github.io/ai-arbiter/demo.en.html) | [Una giornata alla Nordwind](https://viciuslio.github.io/ai-arbiter/demo.it.html) |
| **What it is**, for people who are not developers | [Arbiter in brief](https://viciuslio.github.io/ai-arbiter/arbiter.en.html) | [Arbiter in breve](https://viciuslio.github.io/ai-arbiter/arbiter.it.html) |

**Contents:** [the problem](#the-problem) · [what it does](#what-arbiter-does) ·
[what it is not](#what-it-is-not) · [try it](#try-it-in-two-minutes) ·
[what is inside](#what-is-inside) · [documentation](#documentation) ·
[status](#status-and-roadmap) · [questions](#hard-questions) ·
[contributing](#contributing-and-security)

## The problem

The EU AI Act, and most internal policies, ask an organisation to know which AI systems
it runs, what they are for and how risky they are. That knowledge usually lives in a
list someone wrote once. The list says what was remembered that day, not what happens
today: a tool switched to another model, a retired system that still answers, a team
using a model nobody declared.

Gateways for language models see the traffic and know nothing of the law. Governance
tools hold the inventory and never see the traffic. Arbiter joins the two.

## What Arbiter does

| | |
|---|---|
| **Declares** | An inventory of AI systems, each with the role the organisation has for it |
| **Classifies** | An indicative AI Act tier for each system, with the provision and the date behind every outcome. Rules are data; a person confirms or overrides |
| **Controls** | A gateway in front of models, MCP tools and A2A agents: approved models only, personal data masked, budgets, grants. Your own rules are a file |
| **Records** | Every decision in a log that can be verified. No prompt, argument or answer is stored |
| **Compares** | What was declared against what the traffic shows. What does not match is a finding for a person to judge, and undeclared use is named |
| **Reports** | A daily digest and reports, in English and Italian, as Markdown, HTML or PDF |

The gateway and the toolkit each work without the other. If you already run an LLM
gateway, keep it: Arbiter imports its records.

## What it is not

- **Not legal advice, and not a certificate.** It never says a system complies.
- **Not a judge of whether a declaration is true.** A tier follows from the answers given.
- **Not all-seeing.** It governs what passes through it or is imported. A service opened
  in a browser is not seen.
- **Not for providers.** It covers the obligations of those who deploy AI systems.
- **Not a dashboard.** A command line, an HTTP API, reports and a digest.

More, and what was and was not verified: [scope and limits](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/scope-and-limits.md).

## Try it in two minutes

No Docker, no cloud account, no real model: a mock answers in its place. Needs Python
3.12 or newer.

```bash
pip install "ai-arbiter[gateway,mcp]>=0.1.0a1"
arbiter init                               # a local workspace on SQLite
arbiter demo tour --case consulting --report out/demo.html
```

The last command follows an invented firm that approved one family of models: it prints
thirteen steps and writes the day as [a page like this one](https://viciuslio.github.io/ai-arbiter/demo.en.html).

Write the command as above: the releases so far are pre-releases, and `>=0.1.0a1` lets
`pip` take them for Arbiter only. Do not use `pip install --pre`: that flag also takes
pre-releases of every dependency, and one of them breaks the demonstration.

From a clone instead: `uv sync --all-extras`, then put `uv run` in front of each command.

Your own systems, the gateway as a service, and a live session in front of people:
[getting started](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/getting-started.md) and
[giving a demonstration](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/demo.md).

## What is inside

| Part | What it gives you | Guide |
|---|---|---|
| Gateway | An OpenAI-compatible endpoint with identity, policy as data, redaction, routing, cost metering and budgets | [Gateway](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/gateway.md) |
| Tools and agents | A catalogue and a proxy for MCP servers, a registry and a proxy for A2A agents: nothing is called without a grant, every call is recorded | [Gateway](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/gateway.md) |
| Audit log | One hash chain per tenant, verifiable and exportable, with no content and no names | [Audit log](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/audit.md) |
| Compliance toolkit | Inventory, AI Act classifier, review, scanner, findings, discovery, importers, digest and reports | [Compliance toolkit](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/compliance.md) |
| Demonstrations | A guided tour, a use case told as a story, three scenarios with expected outcomes | [Demonstration](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/demo.md) |

The base install is the toolkit and the command line on SQLite. The rest is optional:

| Extra | Adds |
|---|---|
| `gateway` | The HTTP service, PostgreSQL, calls to providers |
| `mcp`, `a2a` | The proxies for tools and for agents |
| `pii` | Detection of names and places in prompts, run locally |
| `pdf` | Reports as PDF |
| `otel` | Tracing |
| `all` | Everything above |

## Documentation

| I want to | Read |
|---|---|
| Install it and make a first request | [Getting started](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/getting-started.md) |
| Show it to someone | [Giving a demonstration](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/demo.md) |
| Know what it covers and what it does not | [Scope and limits](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/scope-and-limits.md) |
| Configure the gateway, the proxies, budgets | [Gateway](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/gateway.md) |
| Declare systems, classify, scan, report | [Compliance toolkit](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/compliance.md) |
| Understand and verify the audit log | [Audit log](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/audit.md) |
| See how well personal data is detected | [PII evaluation](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/pii-evaluation.md) |
| Understand the design | [Architecture](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/architecture/README.md) and the [decision records](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/adr/README.md) |
| See what changed | [Changelog](https://github.com/ViciusLio/ai-arbiter/blob/main/CHANGELOG.md) |

## Status and roadmap

| Version | Content | State |
|---|---|---|
| 0.1 | Gateway, compliance toolkit, importers, discovery, reports | Built. On PyPI as a pre-release. `0.1.0` waits for a legal review of the rule pack |
| 0.2 | Tools (MCP) and agents (A2A), the demonstrations | Built, part of the same alpha |
| 0.3 | Deployment on Azure, observability, hardening | Not started |
| 1.0 | Documentation and packaging for adopters | Not started |

Only pre-releases are on PyPI. Phase by phase, with what each one left open and every
improvement that was noted: [status and tracking](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/status.md).

## Hard questions

"Another LLM gateway?", "Can a YAML file read the AI Act?", "Was this written by an
AI?", "Is it safe in front of my keys?": the objections a careful reader will raise are
answered, without varnish, in [hard questions](https://github.com/ViciusLio/ai-arbiter/blob/main/docs/questions.md).

## Contributing and security

Issues and pull requests are welcome: [how to contribute](https://github.com/ViciusLio/ai-arbiter/blob/main/CONTRIBUTING.md). Report a
vulnerability privately: [security policy](https://github.com/ViciusLio/ai-arbiter/blob/main/SECURITY.md).

## Licence and name

Apache-2.0: see [LICENSE](https://github.com/ViciusLio/ai-arbiter/blob/main/LICENSE). The distribution is `ai-arbiter`, the command is
`arbiter`. It is not related to `arbiter-ai` or `arbiter` on PyPI, which are other
projects by other authors. Model and product names that appear in
examples and documents are trademarks of their owners, who have no relation to this
project.

*Arbiter is a support tool. It does not provide legal advice.*
