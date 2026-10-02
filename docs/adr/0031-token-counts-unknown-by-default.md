---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0031: Leave token counts unknown when a provider returns no usage, with an opt-in estimate

## Context and Problem Statement

Metering and budgets rely on the token counts a provider returns. Some providers omit
them, most often in streamed responses, and a stream can be cut before the usage arrives.
Arbiter then has to choose between recording nothing, guessing, or counting tokens
itself.

## Considered Options

- **A.** Leave the counts unknown; record the interaction as unpriced.
- **B.** Estimate from the number of characters, and flag the interaction as estimated.
- **C.** Add a tokenizer dependency per model family and count.
- **D.** A by default, with B as an option that the operator enables per deployment.

## Decision Outcome

Chosen option: **D**.

- The gateway always asks for usage: on streamed requests it sets
  `stream_options.include_usage` towards providers that speak the OpenAI wire format. If
  the client did not ask for usage itself, the usage-only chunk is consumed by the
  gateway and not forwarded.
- When no usage arrives and nothing else is configured, token counts and cost are stored
  as unknown. Usage reports show the number of unpriced interactions next to the totals,
  so that a total is never read as complete when it is not.
- A deployment can set `usage_fallback: estimate`. Tokens are then estimated as the
  number of characters divided by `chars_per_token` (default 4), the interaction is
  stored with `usage_estimated` true, and reports show estimated interactions and their
  cost separately from measured ones.
- Hard budgets count what is recorded. With the estimate enabled they count estimates;
  without it, traffic with unknown usage does not consume budget, and the report shows
  how much of it there was.
- No tokenizer is added to the request path.

### Consequences

- Good: by default every number in a FinOps report was measured by a provider.
- Good: an operator who prefers an approximate budget to a blind one can have it, per
  deployment, and the approximation is visible wherever it is used.
- Bad: with the default, a provider that never returns usage escapes hard budgets.
- Bad: a character-based estimate can be far off for languages and content that
  tokenise unlike English prose. The flag is what keeps this honest.

## Pros and Cons of the Options

| Criterion | A. Unknown, unpriced | B. Character estimate, flagged | C. Tokenizer per model family | D. A by default, B opt-in |
|---|---|---|---|---|
| Complexity | Lowest | Low | High | Low |
| Azure cost | None | None | More memory per replica | None |
| Scalability | No cost | Negligible | CPU on the request path | Negligible |
| Security | Hard budgets do not see that traffic | Budgets count an estimate | More precise budgets | The operator chooses |
| Compliance / privacy | Honest reports: unpriced traffic is counted and shown | Risk of reading estimates as measurements | Still an estimate for models not covered | Estimates always flagged and reported apart |
| Maintainability | None | One ratio to tune | Tokenizers to update with every model | Low |
| Lock-in | None | None | On tokenizer libraries | None |

## More Information

- [Data model](../architecture/data-model.md), `INTERACTION.usage_estimated`
- [ADR-0030](0030-price-catalogue-as-versioned-file.md)
