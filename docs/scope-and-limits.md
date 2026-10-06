# Scope and limits

What Arbiter is for, where it stops, and what has and has not been verified. Read this
before relying on it.

> Arbiter is a support tool. It does not provide legal advice.

## The problem

An organisation that uses AI is asked, by the EU AI Act and by its own rules, to know
which AI systems it runs, what they are for and how risky they are. In practice that
knowledge lives in a list someone wrote once. The list says what was remembered that
day. It does not say what happens today: a tool switched to another model, a retired
system that still answers, a team that started using a model nobody declared.

Tools exist for each half of this. Gateways for language models see the traffic and know
nothing of the law. Governance tools hold the inventory and never see the traffic.

## What Arbiter does about it

It links the two: an inventory of AI systems classified under the AI Act, and the
traffic those systems actually produce.

- A **gateway** stands between applications and models (and the tools and agents they
  reach). It applies rules that are data, masks personal data, meters cost, and writes
  every decision to a log that can be verified.
- A **compliance toolkit** holds the inventory, proposes a risk tier for each system
  with the provision and the date behind it, and compares what was declared with what
  the traffic shows. What does not match becomes a finding for a person to judge.

Each half works without the other. Together they answer one question: does what we say
we run match what we run?

## Who it is for

- The person who answers for AI in an organisation that deploys AI systems built by
  others: a compliance, risk or security function, or the head of a small technical team.
- The engineers who would otherwise put that person's rules into each application.

It is built for organisations in scope of the AI Act as **deployers**. It runs on one
machine with SQLite, or as a service with PostgreSQL.

## What is in scope

| In scope | How |
|---|---|
| Requests to language models through an OpenAI-compatible endpoint | The gateway |
| Calls to tools over MCP and to agents over A2A | Two proxies, with a catalogue and grants |
| Records of another LLM gateway | Importers (LiteLLM, JSON lines), without content |
| The obligations of a deployer under the AI Act | A rule pack written from the Official Journal |
| An organisation's own rules about models, data, budgets and tools | A policy pack, as a file |

## What is out of scope

- **Legal advice and certification.** Arbiter never says a system complies. It says
  "indicative" and "no findings", and a person decides.
- **Whether a declaration is true.** A classification follows from the answers given.
  The traffic contradicts some of them, not all.
- **Traffic that does not pass through it.** A tool that talks to its vendor directly, or
  a service opened in a browser, is not seen. Reading network logs is planned, not built
  ([ADR-0058](adr/0058-network-logs-as-a-source-of-discovery.md)).
- **The obligations of providers** of AI systems and of general-purpose AI models.
- **The content of conversations.** It is not stored and not analysed after the fact;
  only what is needed to decide is read, in memory, before a request leaves.
- **Model quality, safety evaluation, prompt engineering.** Other tools do this.
- **A user interface.** There is a command line, an HTTP API, reports and a digest. No
  dashboard.

## Limits you should know

- **A classification is indicative, not a legal conclusion.** It follows from the facts
  you declare; nothing checks that they are true. The rule pack covers the obligations
  of deployers, not of providers, and not general-purpose AI models. It was written from
  the Official Journal text; its comparison with EUR-Lex by the project owner is still
  pending, and every output says so.
- **Detection of personal data is by format by default.** The built-in detectors find
  e-mail addresses, phone numbers (international and Italian), IBANs, payment cards,
  Italian fiscal codes and VAT numbers, IP addresses and common credential formats. An
  optional local plugin adds names and places written in words (ADR-0055). On about
  fifty invented sentences per language it raised recall from 14-17% to 81-93%, with a
  precision of 93-97% ([figures and limits](pii-evaluation.md)). Neither finds
  dates of birth or health data, and no figure here is a promise about your prompts.
- **Costs are estimates**, computed from a price catalogue you fill in. Arbiter ships no
  prices for real providers.
- **The audit log is tamper-evident, not tamper-proof.** Someone who can write to the
  database can rewrite the whole chain; keep a copy of the head elsewhere.
- **Provider adapters.** The OpenAI-compatible adapter was checked by hand against one
  local server (Ollama); the Azure OpenAI adapter only against a simulated transport.
  Neither has been run against a hosted service.
- **Importers.** The LiteLLM importer follows the format LiteLLM documents. It has not
  read the output of a live LiteLLM.
- **Discovery is as fine as a project.** A project that runs several systems shows as
  one candidate, and nothing is declared for you.
- **E-mail.** The SMTP notifier was checked against a mail catcher over plain SMTP.
  STARTTLS, TLS and authentication are covered by tests that replace the client, not by
  a server. The default notifier writes files and sends nothing.
- **PDF is an extra.** Reports are Markdown and HTML; `--format pdf` needs the extra
  `pdf` and the Pango library of the operating system, works on the command line only
  and is not in the container image. The digest has no PDF output.
- **MCP proxy.** It speaks revision `2026-07-28` over Streamable HTTP only and does not
  inspect the content of a call. It was tested with the client and a server of the
  official Python SDK, joined in process; no server or client of another vendor, and
  nothing over a real network, has gone through it yet.
- **A2A.** A signature counts only against keys you configured; signing is optional in
  A2A, so many cards will be `unsigned`, and by default that does not stop a call. gRPC
  is not proxied. The proxy was tested with the client and a server of the official
  Python SDK, joined in process, on both bindings; no real agent on a network has gone
  through it yet. The client of the SDK shows a refusal as HTTP 403, without its reason.

## What was verified, and how

| Claim | Evidence |
|---|---|
| The code does what its tests say | More than 1,100 automated tests on Python 3.12, 3.13 and 3.14, on SQLite and PostgreSQL, on Linux and Windows; coverage above 95% |
| No prompt text is stored | A test searches the whole database for the text of the requests it sent |
| The package installs and runs on its own | The wheel was installed alone in a clean environment and ran the demonstrations |
| The MCP and A2A proxies speak the protocols | The clients and servers of the two official Python SDKs were joined through them, in process |
| The dates and provisions of the rule pack | Read on the Official Journal text, pinned by checksum |

| Not verified | |
|---|---|
| The legal correctness of the rule pack | No person with legal training has reviewed it |
| Real providers | One local server (Ollama) by hand; no hosted service, no Azure OpenAI endpoint |
| Real tools, agents and coding products | Stand-ins and the official SDKs only; nothing over a real network |
| Use in production | None that the project knows of |
| An independent security review | None |

## Real coding tools and a gateway

The demonstration uses generic tools, "a coding IDE" and "a code assistant", because
whether a product can be put behind a gateway is a fact about each product. Two were
looked up on their vendors' documentation on 2026-10-06. Neither was connected to
Arbiter.

| Product | What its documentation says | What follows |
|---|---|---|
| GitHub Copilot CLI | It can use "any other OpenAI Chat Completions API-compatible endpoint" through `COPILOT_PROVIDER_BASE_URL`, with `COPILOT_MODEL`; the model must support tool calling and streaming ([docs.github.com](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models)) | It could be pointed at Arbiter's gateway. Not tried: tool calling through the gateway is untested |
| Kiro | It offers models of several providers, chosen in the tool; in Kiro Enterprise an administrator selects which models are available to users ([kiro.dev](https://kiro.dev/docs/enterprise/governance/model/)). No setting for another endpoint was found | Its requests would not pass through a gateway. The choice of models is governed in the product; Arbiter would see its use only through network logs, which are planned and not built |

So a rule such as "approved models only" is enforced in different places for different
tools: at a gateway for those that accept one, in the product's own administration for
the others. Arbiter covers the first case and, with the inventory, records the second as
a declared system whose traffic it does not see.

Everything that was noted as weak, and what was done about it, is in
[the status page](status.md).
