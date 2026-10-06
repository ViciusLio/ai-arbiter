# Releasing

Releases are published to PyPI by `.github/workflows/release.yml` using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub proves its
identity to PyPI with a short-lived token, so no API token is stored in the repository.

Publishing is always triggered by the project owner (ADR-0005). The first release is
`0.1.0a1` (ADR-0032); nothing has been published yet. Nothing in CI publishes
on its own.

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

Not checked: the release workflow itself, which has never run, and the upload.

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
2. In a clean environment: `pip install --pre "ai-arbiter[gateway,mcp]"`, then
   `arbiter init` and `arbiter demo tour --case consulting`.
3. Only then change the texts that say nothing is published: the status box and "Status
   and roadmap" in `README.md`, "Install" in `docs/getting-started.md`, and the message of
   a missing extra in `src/ai_arbiter/core/errors.py`.
4. On GitHub, create a release from the tag with the entries of the changelog.

A file uploaded to PyPI can be yanked but never replaced: a mistake is fixed by a new
version, `0.1.0a2`.

## About the first release

The first release takes the name `ai-arbiter` on PyPI. There is no separate
name-reserving release: ADR-0032 replaced the `0.0.1` planned by ADR-0005 with
`0.1.0a1`.

- Before publishing, check that the name is still free:
  <https://pypi.org/project/ai-arbiter/> must return "not found".
- `0.1.0a1` is a pre-release. `pip install ai-arbiter` does not pick it: users install it
  with `pip install --pre ai-arbiter` or `pip install ai-arbiter==0.1.0a1`.
- The release workflow has never run. Expect to fix something the first time.
