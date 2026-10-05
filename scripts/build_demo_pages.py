"""Write the pages of the consulting demonstration that GitHub Pages serves.

    uv run python scripts/build_demo_pages.py

Each page is the record of a real run of `arbiter demo tour --case consulting --report`,
made here in an empty workspace of its own, one for each language, so that every page
shows the day from its beginning. Nothing is edited by hand: to change a page, change
the demonstration and run this again.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

DIRECTORY = Path(__file__).parents[1] / "docs" / "presentation"
PAGES = {"it": "demo.it.html", "en": "demo.en.html"}
STEPS = 13


def say(line: str) -> None:
    sys.stdout.write(line + "\n")


def main() -> int:
    arbiter = Path(sys.executable).parent / "arbiter"
    for locale, name in PAGES.items():
        target = DIRECTORY / name
        with tempfile.TemporaryDirectory() as workspace:

            def run(*arguments: str, cwd: str = workspace) -> str:
                done = subprocess.run(  # noqa: S603
                    [str(arbiter), *arguments], cwd=cwd, capture_output=True, text=True, check=False
                )
                if done.returncode != 0:
                    say(done.stdout + done.stderr)
                    raise SystemExit(f"arbiter {' '.join(arguments)} failed")
                return done.stdout

            run("init")
            page = Path(workspace) / "demo.html"
            run("demo", "tour", "--case", "consulting", "--locale", locale, "--report", str(page))
            text = page.read_text(encoding="utf-8")
        if "http://" in text or "https://" in text:
            raise SystemExit(f"{name}: the page refers to an address outside itself")
        expected = {"it": f"{STEPS} passi su {STEPS}", "en": f"{STEPS} of {STEPS} steps"}[locale]
        if expected not in text:
            raise SystemExit(f"{name}: the run did not go as the demonstration expects")
        target.write_text(text, encoding="utf-8", newline="\n")
        say(f"Wrote {target.relative_to(DIRECTORY.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
