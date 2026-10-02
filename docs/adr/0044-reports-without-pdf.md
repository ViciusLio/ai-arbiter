---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0044: Reports are Markdown and HTML; PDF comes from printing the HTML

## Context and Problem Statement

The brief lists reports "exportable (PDF/Markdown)". Phase 4b delivered the system
report and the audit report in Markdown and HTML. Producing PDF inside Arbiter needs a
rendering library.

## Considered Options

- **1.** No PDF: the HTML report is written to print well, and the guide says how.
- **2.** An optional extra `pdf` built on WeasyPrint.
- **3.** Decide in Phase 7 (packaging).

## Decision Outcome

Chosen option: **1**. The HTML reports carry a print style sheet; a browser prints them
to PDF. The brief is not edited: this record is the change.

### Consequences

- Good: no new dependency, and the base install keeps producing every report.
- Bad: a PDF cannot be produced by a scheduled job without a browser. If that is needed
  later, option 2 can be added as an extra without changing the reports.

## Pros and Cons of the Options

| Criterion | 1. Print the HTML | 2. Extra with WeasyPrint | 3. Decide later |
|---|---|---|---|
| Complexity | Low | Medium: system libraries in the image | None now |
| Azure cost | None | A larger image | None |
| Scalability | Not relevant | Rendering is slow for long audit reports | Not relevant |
| Security | No new code | A rendering engine parses HTML | No change |
| Compliance / privacy | No change | No change | No change |
| Maintainability | One template per format | A third output to test, native libraries to track | An open item |
| Lock-in | None | On the library | None |

## More Information

- [ADR-0025](0025-docker-free-local-development.md),
  [ADR-0040](0040-deferrable-items-before-0-1-0.md)
