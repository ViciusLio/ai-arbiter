# Network and SASE: preparation

- **Status**: prepared on 2026-10-05; a wish of the project owner (I-48), with no date.
  No code exists and none is written before the decisions below
- **Date**: 2026-10-05
- **Inputs**: the importers and the discovery of Phase 4b
  ([ADR-0019](../adr/0019-external-telemetry-ingestion.md),
  [ADR-0042](../adr/0042-discovered-systems-by-project.md)); the documentation of four
  vendors, read on their own sites
- **Expected output from the project owner**: the decisions N1 to N7, when the work is
  wanted

> Arbiter is a support tool and does not provide legal advice.

## 1. Why

Arbiter compares what an organisation declares with what its traffic shows. Today the
traffic it knows is what passes through its own gateway, and what is imported from
another LLM gateway. A person who opens an AI service in a browser, or a tool that
calls a model directly, is invisible to it.

An organisation with a secure web gateway, a CASB or a SASE service already has that
other half: a log of who reached which destination, often with the application and its
category already recognised. Two links are possible.

| Direction | What it gives |
|---|---|
| In: the network logs are read by Arbiter | AI use that does not pass through Arbiter shows as candidate systems and findings, next to the declared inventory |
| Out: Arbiter's lists go to the network | The destinations the organisation approved, and the ones it refused, are enforced where the traffic actually flows |

## 2. What the vendors' logs hold, checked on their own sources

Read on 2026-10-05. Only what was read is listed; see the end of the section for what
was not.

### Cloudflare Zero Trust: Gateway HTTP dataset (Logpush)

| Fact | Source |
|---|---|
| Fields: `Datetime`, `Email`, `UserID`, `DeviceID`, `DeviceName`, `URL`, `HTTPHost`, `DestinationIP`, `DestinationPort`, `HTTPMethod`, `Action`, `PolicyName` | `developers.cloudflare.com/logs/logpush/logpush-job/datasets/account/gateway_http/` |
| The application and the category are already recognised: `ApplicationNames`, `ApplicationIDs`, `CategoryNames`, `CategoryIDs`, each a list | Same page |

### Zscaler Internet Access: NSS feed for web logs

| Fact | Source |
|---|---|
| A feed is a line per transaction built from field specifiers chosen by the administrator. The output type is JSON by default; tab-separated and custom delimiters can be chosen | `help.zscaler.com`, "NSS Feed Output Format: Web Logs" |
| Fields: `%s{time}`, `%d{epochtime}`, `%s{login}` (an e-mail address), `%s{dept}`, `%s{url}` (without the scheme), `%s{host}`, `%s{urlcat}`, `%s{urlsupercat}`, `%s{urlclass}`, `%s{appname}`, `%s{appclass}`, `%s{action}`, `%s{reason}`, `%s{rulelabel}`, `%d{reqsize}`, `%d{respsize}`, `%s{activity}`, `%s{app_risk_score}` | The field list published with that page (CSV dated 2025-05-07) |
| **A feed can carry the text a person typed**: `%s{prompt_req}` is "the prompt entered by the user in the generative AI application" | Same list |

### Netskope: transaction events

| Fact | Source |
|---|---|
| The format is W3C Extended Log File Format. Formats 1 to 4 exist, and a "Universal" format in which the fields of an export are chosen (197 fields at the time of reading) | `docs.netskope.com/en/transaction-events-formats` |
| Fields: `date`, `time`, `cs-username` or `x-c-authn-user`, `cs-host`, `x-cs-url`, `x-cs-app`, `x-cs-app-category`, `x-cs-app-activity`, `x-policy-action`, `cs-bytes`, `sc-bytes` | Same page |
| Delivery: an event streaming client, or log streaming straight to cloud storage. Events can also be pulled page by page from the REST API (`/api/v2/events/dataexport/events/page`) | Same page; "Get Events Data" |

### Microsoft Defender for Cloud Apps: cloud discovery

| Fact | Source |
|---|---|
| It reads the logs of many firewalls and proxies, and a custom parser maps the columns of any other log. The fields it needs: date of the transaction, source IP, source user, destination IP, destination URL, total data, uploaded or downloaded data, action taken | `learn.microsoft.com/en-us/defender-cloud-apps/custom-log-parser`, `set-up-cloud-discovery` |
| Its catalogue has a category "Generative AI", usable as a filter on discovered apps | `learn.microsoft.com/en-us/microsoft-365/copilot/manage-generative-ai-apps` |
| A cloud discovery API exists | `learn.microsoft.com/en-us/defender-cloud-apps/api-discovery` |

### What the four have in common

Every one gives, per transaction: a time, a person, a destination host, an action
(allowed or blocked), and in three cases out of four an application name and a category
assigned by the vendor. That is the same shape as Arbiter's canonical telemetry record
minus the model and the tokens, which a network log cannot know.

### Not verified

- Cisco Umbrella: the page of its log formats was reached, but the field lists were not
  read. Palo Alto Prisma Access, Fortinet and Check Point were not looked at.
- How each vendor names the category of generative AI services in its logs, and how
  complete that category is. Only Microsoft's name was read.
- Any API to write a list of destinations into a vendor's policy.
- Nothing was run: no log of a real tenant was seen. Every field above comes from a
  documentation page, as the LiteLLM mapping did (I-31).

## 3. Three things that shape the design

**Content.** A Zscaler feed can hold prompts. Arbiter stores no prompt unless a system
opted in, and its importers drop content on the way in: an importer of network logs must
do the same, and must not fail when such a field is present. It should say in its output
that a field with content was found and dropped.

**People.** A network log names a person on every line. Arbiter's own records name a
key, a project and a team. Importing a browsing log per person turns a compliance tool
into a monitoring tool for employees, which in several member states needs an agreement
or a notice before it is done. That is a question for the organisation's legal advice,
not one Arbiter can answer; the design can make the cautious choice the default.

**What counts as AI.** A network log covers everything a person opens. Only the lines
about AI services belong in Arbiter, and something has to say which those are: the
vendor's category, or a list of Arbiter's own.

## 4. Where it would fit

No new part of the architecture is needed for the inbound direction.

| Piece | Today | With network logs |
|---|---|---|
| A source of records | `compliance/ingest/sources.py`: `jsonl`, `litellm`, behind the port `TelemetrySource` | One more source, or one per vendor |
| A record | Model, provider, tokens, a group, labels; no content | Destination and application in place of model and provider; no tokens |
| Discovery | Groups unattributed requests by project or by the group of a source, 30 days | The group is the department or the team of the log |
| Findings | `SCAN-UNDECLARED-SYSTEM-CANDIDATE`, `SCAN-UNATTRIBUTED-TRAFFIC` | The same, and possibly one for a refused destination that is still reached |

The outbound direction is new: a list of destinations derived from the inventory and
from the policy, written as a file or pushed through an API.

## 5. Decisions for the owner

Azure cost is none for every option. Recommendations are marked.

### N1: which direction first

| # | Option | Complexity | Security and privacy | Lock-in |
|---|---|---|---|---|
| 1 | In only: read network logs **(recommended)** | Medium | Reads data that names people: see N4 | None |
| 2 | In and out together | High | Out changes what a network blocks: a wrong list stops work | Per vendor on the way out |
| 3 | Out only | Medium | No personal data read | Per vendor |

### N2: the input format

| # | Option | Complexity | Maintainability |
|---|---|---|---|
| 1 | One generic "web access log" source: CSV or JSON lines, with the mapping of columns written in the configuration | Low | One parser; every user writes a mapping |
| 2 | One importer per vendor | High | Each follows a vendor's changes |
| 3 | The generic source, plus ready mappings for the vendors read above, as data **(recommended)** | Medium | One parser; the mappings are data and can be corrected without code |

### N3: how a line is recognised as AI use

| # | Option | Complexity | Limit |
|---|---|---|---|
| 1 | The vendor's application and category fields | Low | As complete as the vendor's catalogue; absent from some logs |
| 2 | A list of AI destinations shipped with Arbiter as a data pack, with its date | Medium | Goes stale; has to be maintained |
| 3 | The vendor's category when present, the list otherwise **(recommended)** | Medium | Two sources to explain in the output |

### N4: the person in the log

| # | Option | Privacy | What is lost |
|---|---|---|---|
| 1 | Keep the person, as a keyed hash | A pseudonym is still personal data | Nothing |
| 2 | Drop the person at import and keep the department or group only **(recommended as the default)** | No person stored | Who to talk to; the organisation finds that in its own log |
| 3 | Configurable, with 2 as the default | The operator decides, and the output says which | Nothing |

### N5: how the logs arrive

| # | Option | Complexity | Security |
|---|---|---|---|
| 1 | A file given to `arbiter ingest`, as for the other sources **(recommended)** | Low | No credential of the vendor in Arbiter |
| 2 | Arbiter pulls from the vendor's API or bucket | High | Holds a credential that reads the whole browsing log |
| 3 | Arbiter receives a push (HTTP or syslog) | High | A new endpoint that accepts data from outside |

### N6: the outbound list, when it is wanted

| # | Option | Complexity | Lock-in |
|---|---|---|---|
| 1 | A file: hosts approved and hosts refused, for a person to load as a custom category **(recommended)** | Low | None |
| 2 | Pushed through each vendor's API | High | Per vendor; not verified that such APIs exist |

### N7: when

| # | Option |
|---|---|
| 1 | After 0.3 (Azure), as first noted **(recommended)** |
| 2 | Before Phase 6, as an addition to 0.2 |
| 3 | Only the generic source of N2 now, the rest later |

## 6. Suggested answer

```text
N1: 1 (in only: read network logs)
N2: 3 (a generic source plus ready mappings as data)
N3: 3 (the vendor's category, a list of Arbiter's own otherwise)
N4: 2 (drop the person, keep the department or group)
N5: 1 (a file given to arbiter ingest)
N6: 1 (a file of approved and refused hosts, later)
N7: 1 (after 0.3)
```

---

*Arbiter is a support tool and does not provide legal advice.*
