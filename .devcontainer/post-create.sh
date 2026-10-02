#!/usr/bin/env bash
# Runs once, when the development container is created (ADR-0026).
set -euo pipefail

echo "==> Installing Python 3.12, 3.13 and 3.14"
uv python install 3.12 3.13 3.14

echo "==> Installing the project with every extra (Python 3.12, see .python-version)"
uv sync --all-extras

echo "==> Tool versions"
uv --version
uv run python --version
docker --version || echo "docker is not ready yet; it starts with the container"

cat <<'EOF'

Ready. Verify the environment with:

  uv run pytest                 # SQLite and PostgreSQL
  scripts/check.sh              # every check, on every supported Python

EOF
