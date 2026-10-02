# Releasing

Releases are published to PyPI by `.github/workflows/release.yml` using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub proves its
identity to PyPI with a short-lived token, so no API token is stored in the repository.

Publishing is always triggered by the project owner (ADR-0005). Nothing in CI publishes
on its own.

## One-time setup

Done by the project owner, before the first release.

1. **Push the repository to GitHub**: <https://github.com/ViciusLio/ai-arbiter>. The
   project links in `pyproject.toml` already point there.
2. **Get CI green on `main`.** The workflows have not run before the first push.
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

## Releasing a version

1. Make sure `main` is green in CI.
2. Set the version in `pyproject.toml` and move the `[Unreleased]` entries of
   `CHANGELOG.md` under a heading for that version, with the date.
3. Commit: `chore(release): 0.0.1`.
4. Tag and push:

   ```bash
   git tag v0.0.1
   git push origin main v0.0.1
   ```

5. The workflow checks that the tag matches the version, builds the distributions,
   installs the wheel in a clean environment and runs it, then waits for approval of the
   `pypi` environment and publishes.

## About the 0.0.1 release

`0.0.1` exists to take the name `ai-arbiter` on PyPI (ADR-0005). PyPI may remove packages
that are empty or have no functionality (PEP 541), so `0.0.1` is a real, if small,
release: it installs a working `arbiter` command (`init`, `config show`, `plugins list`,
`db`, `serve`), ships the README and the licence, and links to the repository.

Before publishing `0.0.1`, check that the name is still free:
<https://pypi.org/project/ai-arbiter/> must return "not found".
