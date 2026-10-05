---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0057: Reports as PDF through an optional extra

Supersedes [ADR-0044](0044-reports-without-pdf.md).

## Context and Problem Statement

ADR-0044 left PDF to the print dialog of a browser, and named its cost: a scheduled job
cannot print. The owner now asks for PDF output of the reports (I-36). The reports
already exist as HTML with a print style sheet; what is missing is something that turns
that HTML into a file without a person.

## Considered Options

- **1.** WeasyPrint as an optional extra: it renders the HTML that exists.
- **2.** A headless browser driven by Playwright: the same result as printing by hand.
- **3.** A PDF library in pure Python that draws the pages: a second layout.
- **4.** No PDF, as ADR-0044 decided.

## Decision Outcome

Chosen option: **1**, as recommended and confirmed by the owner on 2026-10-05.

- The extra `pdf` installs WeasyPrint. `arbiter report system KEY --format pdf -o DIR`
  and `arbiter report audit --format pdf -o DIR` render the HTML report and convert it.
- The base install is unchanged: without the extra the command says which extra is
  missing, and Markdown and HTML keep working.
- The converter is given the HTML as a string and may fetch nothing: a report is one
  self-contained document, and a rendering engine that follows addresses found in data
  typed by people would be a way out of the network.
- WeasyPrint needs the Pango library of the operating system. The development container
  installs it. The container image of the project does not include the extra: the image
  stays as small as it is (I-11), and PDF from the image is a later choice.

### Consequences

- Good: a scheduled job can write a PDF.
- Good: one layout. A change to the HTML report changes the PDF.
- Bad: a system library is needed, and installing it on Windows takes more than `pip`.
  A test that renders a real PDF is skipped where the library is missing.
- Bad: PDF is on the command line only. The HTTP API serves Markdown and HTML.
- Bad: rendering a long audit report is slow; not measured.

## Pros and Cons of the Options

| Criterion | 1. WeasyPrint | 2. Headless browser | 3. Pure Python drawing | 4. No PDF |
|---|---|---|---|---|
| Complexity | Low: a few lines around the HTML | Medium: a browser to install and start | High: a second layout | None |
| Azure cost | None while it stays out of the image | A much larger image | None | None |
| Scalability | Slow on long reports | Slower, a process per rendering | Fast | Not relevant |
| Security | A rendering engine parses HTML; fetching is switched off | A whole browser parses HTML | No HTML parsed | No new code |
| Compliance / privacy | Rendered locally | Rendered locally | Rendered locally | No change |
| Maintainability | One layout; a system library to document | One layout; a browser to keep current | Two layouts to keep alike | Nothing |
| Lock-in | Replaceable: the input is HTML | Replaceable | The layout is tied to the library | None |

## More Information

- [ADR-0025](0025-docker-free-local-development.md): the project still builds, tests
  and runs with no container runtime and without this extra
- WeasyPrint 70.0 was the version installed and tried when this was written
