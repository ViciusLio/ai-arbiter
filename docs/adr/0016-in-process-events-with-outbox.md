---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0016 — Use an in-process event bus with a transactional outbox; add Service Bus in Phase 6

## Context and Problem Statement

Gateway and compliance modules must not import each other (ADR-0010) yet compliance reacts
to gateway traffic. They communicate through events. The brief names Azure Service Bus or
Event Grid for asynchronous events; ADR-0008 keeps development local until Phase 6, and
the CLI must work with no broker at all.

## Considered Options

- **A.** `EventBus` port with an in-process implementation and a transactional outbox
  table; an Azure Service Bus adapter in Phase 6.
- **B.** Azure Service Bus from the start, using the official emulator locally.
- **C.** Azure Event Grid.

## Decision Outcome

Chosen option: **A**, with **Service Bus** as the Azure implementation in Phase 6.

- Events are written to `outbox_event` in the same transaction as the state change that
  caused them. A dispatcher delivers them to subscribers and marks them dispatched.
- Delivery is at-least-once; every handler is idempotent on the event id.
- In the standalone CLI and in tests the dispatcher runs in-process, right after commit.
- Event Grid is not used for internal events. It may be used later to publish selected
  events to external systems.

### Consequences

- Good: no event is lost between a committed change and its publication.
- Good: no broker needed for local development or for the CLI.
- Bad: polling the outbox adds a small delay and database load; tuned in Phase 6.
- Bad: the in-process bus does not exercise real broker behaviour (redelivery, dead
  letters) until Phase 6; the adapter gets contract tests against the emulator then.

## Pros and Cons of the Options

| Criterion | A. In-process + outbox, Service Bus later | B. Service Bus from the start | C. Event Grid |
|---|---|---|---|
| Complexity | Low now, medium later | Medium (emulator in Compose from day one) | Medium |
| Azure cost | None until Phase 6; then Service Bus Standard for topics | Same once deployed | Per operation, low |
| Scalability | One process until Phase 6; competing consumers after | Competing consumers, sessions | Push delivery, high fan-out |
| Security | No extra endpoint | Managed identity and RBAC | Webhook endpoints to secure |
| Compliance / privacy | Events stay in the database; payloads carry ids, not content | Events transit a second store | Same as B |
| Maintainability | One more table and a dispatcher | Emulator upkeep in development | No official local emulator |
| Lock-in | None (port) | Contained by the port | Contained by the port |

## More Information

- [Flows](../architecture/flows.md)
