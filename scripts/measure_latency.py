"""Measure the time the gateway adds to a chat completion.

The mock provider answers at once, so the time of a request is the time spent in Arbiter:
authentication, budgets, PII detection, policy, routing, and the transaction that writes
the interaction, two audit entries, the roll-ups and the outbox event. Requests go
through the real application in process, without a network.

    uv run python scripts/measure_latency.py [--requests 300] [--max-p95-ms 1000]

Runs on SQLite, and on PostgreSQL as well when ARBITER_TEST_DATABASE_URL is set. Prints a
Markdown table; exits 1 if a p95 exceeds ``--max-p95-ms``.
"""

import argparse
import asyncio
import os
import secrets
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.persistence import migrate
from ai_arbiter.core.persistence.tenant import ensure_tenant
from ai_arbiter.gateway.api.app import create_app
from ai_arbiter.gateway.identity.model import PrincipalKind

PROMPT = (
    "Summarise the attached minutes for the steering committee. Contact: "
    "mario.rossi@example.com, +39 347 1234567. " + "The quarterly results were discussed. " * 20
)
BODY = {"model": "mock-small", "messages": [{"role": "user", "content": PROMPT}]}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


async def measure(url: str, requests: int, concurrency: int) -> list[float]:
    await migrate.upgrade_async(url)
    settings = load_settings(
        database={"url": url},
        deployments=[{"name": "mock", "provider": "mock", "model": "mock-small"}],
        redaction={"key": "secret://redaction-key"},
        logging={"level": "WARNING"},
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://arbiter.test") as client,
        ):
            runtime = app.state.runtime
            async with runtime.database.transaction() as session:
                tenant = await ensure_tenant(session, slug="latency", name="Latency")
                team = await runtime.identity.create_team(session, tenant.id, "t")
                project = await runtime.identity.create_project(session, tenant.id, team.id, "p")
                principal = await runtime.identity.create_principal(
                    session, tenant.id, kind=PrincipalKind.SERVICE, display_name="bench"
                )
                await runtime.identity.grant_role(
                    session, tenant.id, principal_id=principal.id, role=AccessRole.DEVELOPER
                )
                _, key = await runtime.identity.issue_api_key(
                    session, tenant.id, project_id=project.id, principal_id=principal.id, name="b"
                )
            headers = {"Authorization": f"Bearer {key}"}

            async def one() -> float:
                started = time.perf_counter()
                response = await client.post("/v1/chat/completions", json=BODY, headers=headers)
                response.raise_for_status()
                return (time.perf_counter() - started) * 1000

            for _ in range(20):  # warm-up: imports, connections, first pages
                await one()
            timings: list[float] = []
            for _ in range(requests // concurrency):
                timings.extend(await asyncio.gather(*(one() for _ in range(concurrency))))
            return timings
    finally:
        await migrate.downgrade_async(url, "base")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--max-p95-ms", type=float, default=None)
    arguments = parser.parse_args()
    # Throwaway secrets for a throwaway database.
    for variable in ("ARBITER_SECRET_API_KEY_PEPPER", "ARBITER_SECRET_REDACTION_KEY"):
        os.environ.setdefault(variable, secrets.token_urlsafe(48))

    lines = [
        "| Database | Concurrency | Requests | Mean ms | p50 ms | p95 ms | p99 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    worst = 0.0
    with tempfile.TemporaryDirectory() as directory:
        databases = [
            ("SQLite", f"sqlite+aiosqlite:///{(Path(directory) / 'latency.db').as_posix()}")
        ]
        if postgres := os.environ.get("ARBITER_TEST_DATABASE_URL"):
            databases.append(("PostgreSQL", postgres))
        for name, url in databases:
            for concurrency in (1, 10):
                timings = asyncio.run(measure(url, arguments.requests, concurrency))
                p95 = percentile(timings, 0.95)
                if concurrency == 1:
                    worst = max(worst, p95)
                lines.append(
                    f"| {name} | {concurrency} | {len(timings)} | {statistics.fmean(timings):.1f} "
                    f"| {percentile(timings, 0.50):.1f} | {p95:.1f} "
                    f"| {percentile(timings, 0.99):.1f} |"
                )
    sys.stdout.write("\n".join(lines) + "\n")
    if arguments.max_p95_ms is not None and worst > arguments.max_p95_ms:
        sys.stderr.write(
            f"p95 of {worst:.1f} ms without concurrency exceeds {arguments.max_p95_ms} ms\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
