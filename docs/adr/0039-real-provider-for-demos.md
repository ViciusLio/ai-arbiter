---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0039: Use a local model server on demand for demos now, and Azure AI Foundry in Phase 6

## Context and Problem Statement

The owner asked to evaluate GitHub Models as a real provider for demos and manual checks.
Its documentation states that it was fully retired on 30 July 2026, and its inference
endpoint no longer returns completions (checked on 2026-10-02). Demos still benefit from
a real model behind the gateway.

## Considered Options

- **1.** Ollama in a container, started for the demo and removed after.
- **2.** A hosted OpenAI-compatible service with a free tier and a key from the owner.
- **3.** Azure AI Foundry, in Phase 6.
- **4.** No real provider: demos use the mock.

## Decision Outcome

Chosen option: **1 now, and 3 in Phase 6**.

- The rules of ADR-0033 hold: nothing automated depends on a real model, credentials are
  secret references, prompts are synthetic, the server is removed after use.
- The documentation shows the `openai_compat` deployment for a local Ollama server and
  says that with a hosted provider prompts leave the installation.
- Option 2 stays available if the owner names a service; its terms are read first.

### Consequences

- Good: no data leaves the Codespace and no credential is needed.
- Bad: the Ollama image is 9.3 GB and small models answer poorly; a demo shows the
  gateway, not the quality of a model.

## Pros and Cons of the Options

| Criterion | 1. Ollama in a container, started for the demo and removed after | 2. A hosted OpenAI-compatible service with a free tier, with a key from the owner | 3. Azure AI Foundry, in Phase 6 | 4. No real provider: demos use the mock |
|---|---|---|---|---|
| Complexity | Low: checked on 2026-10-02 | Low, after reading that service's terms | Part of the Azure phase | None |
| Azure cost | None | None | Pay per use | None |
| Scalability | Tiny models, slow on two cores | Real models | Real models | Not applicable |
| Security | Nothing leaves the Codespace | A credential to handle | Managed identity later | Nothing |
| Compliance / privacy | No data leaves | Prompts go to a third party, to be stated in the documentation | Prompts go to Azure, region chosen by the owner | Nothing |
| Maintainability | 9.3 GB image to pull each time, about 10 GB of the Codespace disk while it runs | Depends on the free tier lasting | The path the brief asks for | Nothing |
| Lock-in | None | Low | Azure, already the target (ADR-0008) | None |

## More Information

- [Phase 4 preparation](../phases/phase-4-preparation.md), decision P4-6
