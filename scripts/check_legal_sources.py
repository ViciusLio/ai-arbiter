"""Check that the legal texts a rule pack was written from have not changed (ADR-0034).

For each source the pack lists, the document is retrieved again from the Publications
Office of the EU, by CELEX number, and its SHA-256 is compared with the one in the pack.

    uv run python scripts/check_legal_sources.py              # the newest AI Act pack
    uv run python scripts/check_legal_sources.py --version 2026.10.0

A checksum that differs means the published file changed: read what changed before
touching the pack. A checksum that matches does not mean the law is unchanged: a later
amending act or a corrigendum is a new document with its own CELEX number, which this
script cannot find. That search is done by a person, at every release of the pack.

Run by hand; it is not part of the test suite or of CI, which must not depend on a
website. Arbiter is a support tool and does not provide legal advice.
"""

import argparse
import hashlib
import sys
import urllib.request

from ai_arbiter.core.rules import load_packaged_pack

SOURCE_PREFIX = "https://publications.europa.eu/resource/celex/"
# The representation the checksums of the pack were computed on: XHTML, in English.
HEADERS = {"Accept": "application/xhtml+xml", "Accept-Language": "en"}
TIMEOUT_SECONDS = 120


def retrieve(url: str) -> bytes:
    if not url.startswith(SOURCE_PREFIX):
        raise ValueError(f"not a Publications Office address: {url}")
    request = urllib.request.Request(url, headers=HEADERS)  # noqa: S310 - prefix checked above
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        body: bytes = response.read()
    return body


def say(line: str) -> None:
    sys.stdout.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", default="ai-act")
    parser.add_argument("--version", default=None, help="Default: the newest shipped.")
    arguments = parser.parse_args()

    pack = load_packaged_pack(arguments.pack, arguments.version)
    regulation = pack.regulation
    if regulation is None or not regulation.sources:
        say(f"{pack.pack} {pack.version} lists no legal source.")
        return 1
    say(f"{pack.pack} {pack.version}: {regulation.id}, review: {regulation.review}")
    changed = 0
    for source in regulation.sources:
        try:
            found = hashlib.sha256(retrieve(source.url)).hexdigest()
        except (OSError, ValueError) as error:
            say(f"  {source.celex}: NOT RETRIEVED ({type(error).__name__})")
            changed += 1
            continue
        if found == source.sha256:
            say(f"  {source.celex}: unchanged since {source.retrieved}")
        else:
            say(f"  {source.celex}: CHANGED since {source.retrieved}")
            say(f"    in the pack: {source.sha256}")
            say(f"    retrieved:   {found}")
            changed += 1
    say(
        "Still to do by a person: search EUR-Lex for corrigenda and for acts amending "
        f"{regulation.id} published after {regulation.as_of}."
    )
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
