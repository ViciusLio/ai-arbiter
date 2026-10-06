# Hard questions

The objections a careful reader will raise, and the honest answer to each. Where the
answer is "not yet", it says so.

> Arbiter is a support tool. It does not provide legal advice.

## "Another LLM gateway?"

No. Good gateways exist, and Arbiter does not try to beat them at routing, caching or
provider coverage. Its gateway exists to produce evidence for the inventory. If you
already run a gateway, keep it: Arbiter imports its records without their content
(LiteLLM and a JSON lines format today) and compares them with what you declared. The
part that others do not have is the link between traffic and an inventory classified
under the AI Act.

## "A YAML file cannot decide what the AI Act means."

It does not. The rule pack asks questions taken from the text and applies the same
conditions the text states; the result is a proposal with the provision and the date
behind each outcome. Three things keep it honest:

- an unanswered question is never read as "no": while a more severe outcome is still
  possible the tier is `undetermined`;
- nothing is settled until a named person confirms or overrides it, and the engine's
  result is kept next to the person's decision;
- every output says the classification is indicative and that the pack has not been
  reviewed by a person with legal training.

That last point is a real gap. Version `0.1.0` waits for that review
([ADR-0041](adr/0041-legal-review-before-0-1-0.md)); what is published before it is an
alpha and says so.

## "It only works if everything goes through it."

True of the gateway, and stated in [scope and limits](scope-and-limits.md). Two things
reduce the gap: records of another gateway can be imported, and traffic with no declared
system behind it is reported as a candidate system. A tool that talks to its vendor
directly, or a service used in a browser, stays invisible until network logs can be
read, which is decided and not built
([ADR-0058](adr/0058-network-logs-as-a-source-of-discovery.md)).

## "The demonstration names real products. Do they work with it?"

The demonstration is an invented firm that labels its tools with names a reader
recognises. No real product was connected: the demonstration makes each tool's requests
itself. Whether a given product can be pointed at a gateway, and which models it offers,
is for each organisation to check with the vendor; the data, the page and the guide say
so, and the check is an open item (I-50 in [the status page](status.md)). The products
named are trademarks of their owners, who have no relation to this project.

## "Why is Claude the approved model in the example?"

Because the owner of the project chose a single approved family to make the rule easy to
follow. Arbiter has no preference: the list of approved models is a setting, and the
example works the same with any name in it. Much of this project was written with an AI
assistant from the same vendor; see the next question.

## "Was this written by an AI?"

Much of the code and of the documentation was written with an AI coding assistant,
directed and reviewed by the project owner; the commits say so. What that means for you
is what it would mean for any young project: read the tests, not the claims. Every
non-trivial choice is a decision record with the options that were set aside. The test
suite runs on three Python versions and two databases. What was not verified is listed,
not hidden. No independent review has taken place.

## "Is it safe to put in front of my API keys and prompts?"

It is alpha software from one maintainer, and no independent security review has been
done. What it does to limit the damage of its own mistakes:

- prompts and completions are not stored; a test searches the database to check;
- API keys are stored as keyed hashes; provider credentials are read from a secret
  store and never written in configuration;
- a proxy never forwards the caller's key and never follows a redirect;
- a call whose decision cannot be written to the audit log is not forwarded;
- dependencies are audited and the history is scanned for secrets at every push.

The threat model is in [the architecture overview](architecture/README.md). Report a
vulnerability privately: see [SECURITY.md](../SECURITY.md).

## "The audit log can be rewritten by whoever owns the database."

Yes. The chain is tamper-evident, not tamper-proof: a partial change breaks it, a full
rewrite does not. Keep a copy of the head outside the database. Anchoring the head
externally is planned (I-05).

## "Detection of personal data by regular expressions misses most of it."

By default, yes, and the figures are published: on the project's own test sentences the
built-in detectors found 14 to 17% of the personal data, because they look for formats
(e-mail, IBAN, cards, fiscal codes). An optional plugin that runs locally adds names and
places and reached 81 to 93% on the same sentences
([figures and limits](pii-evaluation.md)). The set is small and written by the author of
the detectors; health data is found by neither. Treat redaction as a reduction of
exposure, not as a guarantee.

## "What does it cost in latency?"

About 20 ms added to a request, measured in process against a mock provider, with 17
database statements. The requests of one tenant queue on its audit chain. No measurement
over a real network or with several processes exists yet (I-15, I-16, I-21).

## "Who uses it?"

Nobody that the project knows of. It has never run in production.

## "One maintainer. What if it is abandoned?"

It is Apache-2.0, a single Python package with no service of its own to depend on, and
its data is in your database in a documented schema. The rules are files you can read.
Decisions and their reasons are written down, so that someone else can continue.

## "Python 3.12 or newer only?"

Yes. It is a new project and uses what the language offers now.

## "Is the name not taken?"

`ai-arbiter` is this project. It is not related to `arbiter-ai` or `arbiter` on PyPI,
which are other projects by other authors.
