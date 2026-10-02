---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0015: Support PostgreSQL and SQLite with one portable schema and row-level tenancy

## Context and Problem Statement

The gateway targets Azure Database for PostgreSQL. The CLI is offline-first and cannot
ask a single user to run a database server. The brief also requires multi-tenancy.

## Considered Options

Database:

- **A.** PostgreSQL for the server, SQLite for the standalone CLI, one schema.
- **B.** PostgreSQL only; the CLI keeps results in files.
- **C.** Two separate storage layers.

Tenancy:

- **T1.** Shared schema, `tenant_id` on every table, filter enforced in the data-access
  layer.
- **T2.** Schema per tenant.
- **T3.** Database per tenant.

## Decision Outcome

Chosen options: **A** and **T1**.

- SQLAlchemy 2 async throughout (`asyncpg`, `aiosqlite`); one Alembic history.
- Portable column types only: generic JSON, UTC timestamps, time-ordered UUID keys stored
  as native UUID on PostgreSQL and text on SQLite. No arrays, no dialect-specific
  operators in queries.
- CI runs migrations and the integration suite on both databases.
- `tenant_id` is non-nullable on every tenant-owned table and is the leading column of
  its indexes. The session carries the tenant context and repositories refuse to run
  without it. The standalone CLI uses a single implicit tenant.
- PostgreSQL row-level security is added in Phase 6 as a second barrier.

### Consequences

- Good: the CLI and the server share models, migrations and services.
- Bad: PostgreSQL-only features (JSONB operators, partitioning, `LISTEN/NOTIFY`) are off
  limits in shared code.
- Bad: with T1, isolation depends on application code until row-level security is added.
- **PostgreSQL row-level security is activated in Phase 6** (added at acceptance). It is
  confined to the PostgreSQL adapter: the policies, the migration that creates them and
  the per-transaction tenant setting live there, so shared code and SQLite are unaffected.
  The application-level tenant filter stays in place; row-level security is the second
  barrier, not a replacement.
- Follow-up: large append-only tables (`interaction`, `audit_entry`) may need partitioning
  on PostgreSQL; that would be a PostgreSQL-only migration decided by a later ADR.

## Pros and Cons of the Options

| Criterion | A. PostgreSQL + SQLite | B. PostgreSQL only | C. Two storage layers |
|---|---|---|---|
| Complexity | Medium (portability discipline) | Low | High |
| Azure cost | One Flexible Server | Same | Same |
| Scalability | PostgreSQL in production | Same | Same |
| Security | Local file permissions for SQLite | - | - |
| Compliance / privacy | Local data never leaves the machine | CLI results in ad hoc files | Same as A |
| Maintainability | One model, two CI targets | Simplest | Duplicate logic |
| Lock-in | None | None | None |

| Criterion | T1. Row-level | T2. Schema per tenant | T3. Database per tenant |
|---|---|---|---|
| Complexity | Low | Medium (migrations per schema) | High |
| Azure cost | Lowest | Low | Grows with tenants |
| Scalability | Thousands of tenants | Hundreds | Tens |
| Security | Application-enforced, RLS later | Stronger | Strongest |
| Compliance / privacy | Erasure and export by filter | By schema | By database |
| Maintainability | One migration run | N migration runs | N databases |
| Lock-in | None | PostgreSQL schemas (no SQLite equivalent) | None |

## More Information

- [Data model](../architecture/data-model.md)
