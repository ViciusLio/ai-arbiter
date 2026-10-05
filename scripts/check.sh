#!/usr/bin/env bash
# Runs every check that CI runs, in the same order. Usage:
#
#   scripts/check.sh              # lint, types, import rules, tests on 3.12, 3.13, 3.14,
#                                 # tests without extras, request-path latency
#   scripts/check.sh --containers # also build the image and start the Compose stack
#
# Database tests run on PostgreSQL too when ARBITER_TEST_DATABASE_URL is set (it is, in
# the development container).
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n==> %s\n' "$*"; }

step "Lock file is up to date"
uv lock --check

step "Install (Python $(cat .python-version), all extras)"
uv sync --locked --all-extras --group pii-models

step "Lint"
uv run ruff check .
uv run ruff format --check .
scripts/no-em-dash.sh

step "Types"
uv run mypy

step "Import rules"
uv run lint-imports

step "Tests with coverage (Python $(cat .python-version))"
uv run --group pii-models pytest --cov

for version in 3.13 3.14; do
    step "Tests (Python ${version})"
    UV_PROJECT_ENVIRONMENT=".venv-${version}" uv run --python "${version}" --all-extras pytest -q
done

step "Tests without extras"
UV_PROJECT_ENVIRONMENT=".venv-base" uv run pytest -q

step "Request-path latency against the mock provider"
uv run python scripts/measure_latency.py --max-p95-ms 1000

if [[ "${1:-}" == "--containers" ]]; then
    compose="deploy/compose/compose.yaml"

    step "Build the image"
    docker build -f deploy/docker/Dockerfile -t ai-arbiter:dev .

    step "The image runs as a non-root user"
    test "$(docker run --rm --entrypoint id ai-arbiter:dev -u)" = "10001"

    step "Start the Compose stack"
    trap 'docker compose -f "${compose}" down --volumes' EXIT
    docker compose -f "${compose}" up --no-build --wait --wait-timeout 180

    step "Call the health endpoints"
    curl --fail --silent --show-error http://127.0.0.1:8080/healthz && echo
    curl --fail --silent --show-error http://127.0.0.1:8080/readyz && echo

    step "Send a request through the gateway and verify the audit chain"
    key="$(docker compose -f "${compose}" exec -T arbiter arbiter keys create --name smoke \
        | grep '^arb_')"
    curl --fail --silent --show-error http://127.0.0.1:8080/v1/chat/completions \
        -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" \
        -d '{"model":"mock-small","messages":[{"role":"user","content":"ping"}]}' && echo
    docker compose -f "${compose}" exec -T arbiter arbiter audit verify

    step "Send the digest to the mail catcher of the stack (ADR-0045)"
    scripts/smoke-mail.sh

    step "Run every simulation scenario in the container"
    docker compose -f "${compose}" exec -T arbiter arbiter demo run --all
fi

step "All checks passed"
