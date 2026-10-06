# Security policy

Arbiter is alpha software. It has had no independent security review.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability.

Report it privately through GitHub: on the repository page, **Security**, then
**Report a vulnerability**
(<https://github.com/ViciusLio/ai-arbiter/security/advisories/new>). Say what you found,
how to reproduce it and what it lets someone do. Invented data is enough: never send
real prompts, keys or personal data.

You will get an answer from the maintainer. This is a project of one person, with no
guaranteed response time; a fix and a note in the changelog follow when the report is
confirmed.

## Supported versions

Only the latest release is fixed. Before `0.1.0` there are only pre-releases.

## What is in scope

The code of this repository and the published package: the gateway, the MCP and A2A
proxies, the audit log, the handling of keys and secrets, the command line.

Known limits are not vulnerabilities; they are listed in
[scope and limits](docs/scope-and-limits.md). Two worth knowing: the audit log is
tamper-evident, not tamper-proof, and detection of personal data misses what its
detectors do not look for.
