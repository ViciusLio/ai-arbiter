# Releasing

Releases are published to PyPI by `.github/workflows/release.yml` using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub proves its
identity to PyPI with a short-lived token, so no API token is stored in the repository.

Publishing is always triggered by the project owner (ADR-0005). The first release was
`0.1.0a1` (ADR-0032), on 2026-10-06. Nothing in CI publishes on its own.

## Checked before the first release

On 2026-10-06, on the code of `main`:

| Check | Result |
|---|---|
| The name `ai-arbiter` on PyPI | Free: `https://pypi.org/pypi/ai-arbiter/json` answers 404 |
| `uv build` | A wheel and a source distribution of `0.1.0a1` |
| The description PyPI will show | `twine check` passes; the README uses absolute links |
| The wheel alone, in a clean environment | `arbiter --version`, `init`, `systems apply`, `demo run --all` |
| The wheel with the extras `gateway`, `mcp`, `a2a` | Both guided demonstrations run from the installed package |
| A missing extra | The command names the extra to install |

The release workflow ran for the first time on 2026-10-06 and published `0.1.0a1`. `0.1.0a2`
followed the same day. Right after a release the index may still offer the earlier
version for a minute: the first install tried after `0.1.0a2` took `0.1.0a1`.

## One-time setup

Done by the project owner, before the first release.

1. **Push the repository to GitHub**: <https://github.com/ViciusLio/ai-arbiter>. The
   project links in `pyproject.toml` already point there.
2. **Get CI green on `main`.**
3. **Create the `pypi` environment** in the repository settings (Settings → Environments).
   Adding yourself as a required reviewer makes every publication wait for your approval.
4. **Register a pending trusted publisher on PyPI**
   (Account settings → Publishing → Add a new pending publisher):

   | Field | Value |
   |---|---|
   | PyPI project name | `ai-arbiter` |
   | Owner | `ViciusLio` |
   | Repository name | `ai-arbiter` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   A pending publisher does not reserve the name. The name is taken only when the first
   release is published.

## Before a release that ships a legal rule pack

The check of the legal text is repeated at every release of the pack (ADR-0034):

```bash
uv run python scripts/check_legal_sources.py
```

It retrieves each source of the newest AI Act pack from the Publications Office, as
XHTML in English, and compares its SHA-256 with the one in the pack. It needs the
network, so it is run by hand and is not part of CI.

A checksum that matches does not mean the law is unchanged. A corrigendum or an amending
act is a new document with its own CELEX number: a person searches EUR-Lex for acts
published after the date of the pack. The script ends by saying so.

## Releasing a version

1. Make sure `main` is green in CI.
2. Set the version in `pyproject.toml` and move the `[Unreleased]` entries of
   `CHANGELOG.md` under a heading for that version, with the date.
3. Commit: `chore(release): 0.1.0a1`.
4. Tag and push:

   ```bash
   git tag v0.1.0a1
   git push origin main v0.1.0a1
   ```

5. The workflow checks that the tag matches the version, builds the distributions,
   installs the wheel in a clean environment and runs it, then waits for approval of the
   `pypi` environment and publishes.

## After the first release

1. Open <https://pypi.org/project/ai-arbiter/> and read the page as a stranger would.
2. In a clean environment: `pip install "ai-arbiter[gateway,mcp]==VERSION"`, then
   `arbiter init` and `arbiter demo tour --case consulting`.
3. The install commands in `README.md` and the guides say `>=0.1.0a1`, which is true for
   every later version: they are not edited at a release. Never write the number of a
   version that is not on PyPI yet: on 2026-10-06 the README said `==0.1.0a2` for an
   hour before that version existed, and the command failed.
4. On GitHub, create a release from the tag with the entries of the changelog.

A file uploaded to PyPI can be yanked but never replaced: a mistake is fixed by a new
version, `0.1.0a2`.

## About pre-releases

- `pip install ai-arbiter` does not pick a pre-release. A requirement that names one
  does, for Arbiter only: `pip install "ai-arbiter>=0.1.0a1"`.
- Never tell users to run `pip install --pre`: it takes pre-releases of every dependency
  too. On 2026-10-06 that installed `httpx` 1.0.dev6, another library under the same
  name, and the proxies failed. The instructions of `0.1.0a1` had this mistake; it is
  why `0.1.0a2` exists.
- `0.1.0a1` took the name `ai-arbiter` on PyPI (ADR-0032 replaced the `0.0.1` planned by
  ADR-0005).
