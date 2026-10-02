---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0045: The SMTP notifier is checked against the mail catcher of the Compose stack

## Context and Problem Statement

The unit tests of the `smtp` notifier replace the SMTP client, so they cannot show that
a message reaches a server. The Compose stack already runs Mailpit, a mail catcher that
accepts everything and delivers nothing.

## Considered Options

- **1.** A manual check, once.
- **2.** A step of `scripts/check.sh --containers` and of the container job in CI: send
  the digest to Mailpit and check through its API that the message arrived.
- **3.** Leave the notifier as not verified.

## Decision Outcome

Chosen option: **2**. The step runs `arbiter digest run --send` inside the application
container with the `smtp` notifier pointed at the `mailpit` service, then reads the
Mailpit API and fails when the message is not there.

It checks delivery over plain SMTP on a private network. It does not check STARTTLS,
TLS or authentication, which Mailpit is not configured for: those paths stay covered
only by the tests that replace the client.

### Consequences

- Good: the check is repeated at the end of every phase and on every push.
- Good: no real mail server and no real address is involved.
- Bad: the container job takes a few seconds longer.

## Pros and Cons of the Options

| Criterion | 1. Manual, once | 2. Automated in the Compose check | 3. Not verified |
|---|---|---|---|
| Complexity | Low | Low: a few lines of the script | None |
| Azure cost | None | None | None |
| Scalability | Not relevant | Not relevant | Not relevant |
| Security | No real server | No real server | No change |
| Compliance / privacy | Invented addresses | Invented addresses | No change |
| Maintainability | Goes stale | Repeats itself | A known gap |
| Lock-in | None | Mailpit, replaceable by any catcher | None |

## More Information

- [ADR-0025](0025-docker-free-local-development.md),
  [ADR-0033](0033-real-models-only-in-manual-checks.md)
