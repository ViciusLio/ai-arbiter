"""``arbiter demo``: load a simulation scenario and show what the toolkit makes of it."""

import json
import logging
from importlib import resources
from typing import Annotated

import typer

from ai_arbiter.adapters.mock.tools import mcp_request
from ai_arbiter.cli.common import (
    compliance_for,
    fail,
    open_database,
    reviewer_for,
    run,
    settings_from,
)
from ai_arbiter.cli.demo_consulting import CONSULTING_TENANT, consulting_tour
from ai_arbiter.cli.systems import Locale, translator
from ai_arbiter.compliance.inventory.declarations import parse_declarations
from ai_arbiter.compliance.simulation.model import load_scenario, packaged_scenarios
from ai_arbiter.compliance.simulation.runner import ScenarioResult, run_scenario
from ai_arbiter.core.config.settings import Settings, TrustedKey
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.errors import ArbiterError, MissingExtraError
from ai_arbiter.core.i18n import Translator
from ai_arbiter.core.persistence.tenant import ensure_tenant

app = typer.Typer(help="Simulation scenarios: invented systems and traffic.", no_args_is_help=True)

# Scenarios are loaded here and nowhere else, so that invented data never mixes with
# an organisation's own.
DEMO_TENANT = "demo"
DEMO_REVIEWER = "Demo reviewer"
CASES = ("general", "consulting")


@app.command("list")
def list_scenarios(locale: Locale = "en") -> None:
    """List the scenarios shipped with Arbiter."""
    t = translator(locale)
    for name in packaged_scenarios():
        scenario = load_scenario(name)
        typer.echo(f"{name:<22} {scenario.title.text(locale)}")
        typer.echo(f"{'':<22} {scenario.description.text(locale)}")
    typer.echo("")
    typer.echo(t.text("demo.invented"))
    typer.echo(t.text("disclaimer"))


async def _run(settings: Settings, names: list[str]) -> list[ScenarioResult]:
    compliance = compliance_for(settings)
    scenarios = [load_scenario(name) for name in names]
    async with open_database(settings) as database, database.transaction() as session:
        tenant = await ensure_tenant(session, slug=DEMO_TENANT, name="Demo")
        reviewer = await reviewer_for(session, tenant.id, DEMO_REVIEWER)
        return [
            await run_scenario(session, tenant.id, compliance, scenario, reviewer_id=reviewer)
            for scenario in scenarios
        ]


def _print(result: ScenarioResult, t: Translator, locale: str) -> None:
    scenario = result.scenario
    typer.echo(f"{scenario.scenario}: {scenario.title.text(locale)}")
    typer.echo(scenario.description.text(locale))
    typer.echo("")
    for system in result.systems:
        mark = t.text("demo.as_expected") if system.as_expected else t.text("demo.differs")
        typer.echo(f"  {system.key:<28} {t.text('tier.' + system.tier):<26} {mark}")
        for rule in system.findings:
            typer.echo(f"      {rule}")
        if not system.findings:
            typer.echo(f"      {t.text('digest.no_findings')}")
        if not system.as_expected:
            typer.echo(
                "      "
                + t.text(
                    "demo.expected",
                    tier=t.text("tier." + system.expected_tier),
                    findings=", ".join(system.expected_findings) or "-",
                )
            )
    if result.candidates or result.expected_candidates:
        mark = (
            t.text("demo.as_expected")
            if result.candidates == result.expected_candidates
            else t.text("demo.differs")
        )
        typer.echo(
            f"  {t.text('demo.candidates', names=', '.join(result.candidates) or '-')}  {mark}"
        )
    typer.echo("")


@app.command("run")
def run_demo(
    ctx: typer.Context,
    name: Annotated[
        str | None, typer.Argument(help="Scenario to load. See: arbiter demo list")
    ] = None,
    every: Annotated[bool, typer.Option("--all", help="Load every scenario.")] = False,
    locale: Locale = "en",
) -> None:
    """Load a scenario into the tenant ``demo``, classify, scan, and compare the result
    with what the scenario expects. Safe to repeat. No other tenant is touched.
    """
    t = translator(locale)
    if every == (name is not None):
        raise fail(ArbiterError("name a scenario, or use --all: arbiter demo list"))
    names = packaged_scenarios() if name is None else [name]
    results = run(_run(settings_from(ctx), names))
    for result in results:
        _print(result, t, locale)
    typer.echo(t.text("demo.next", tenant=DEMO_TENANT))
    typer.echo(t.text("demo.invented"))
    typer.echo(t.text("disclaimer"))
    if not all(result.as_expected for result in results):
        raise fail(ArbiterError(t.text("demo.mismatch")))


async def _tour(settings: Settings, t: Translator) -> list[tuple[str, bool, str]]:
    """Walk through the gateway and the toolkit in one process, on invented data.

    Returns, for each step, its title, whether it went as the demonstration expects, and
    what was observed. Nothing leaves the process: the model, the MCP server and the
    agent are stand-ins.
    """
    try:
        import httpx

        from ai_arbiter.gateway.api.app import create_app
    except ImportError as exc:
        raise MissingExtraError("gateway", "The guided demonstration") from exc
    from ai_arbiter.adapters.a2a.signing import CardSigningKey
    from ai_arbiter.adapters.mock.tools import (
        DEMO_CARD,
        DEMO_CARD_URL,
        DEMO_MCP_URL,
        MockToolWorld,
    )

    world = MockToolWorld()
    signing: CardSigningKey | None
    try:
        signing = CardSigningKey("demo-key")
        world.card = signing.sign(DEMO_CARD)
        trusted = (*settings.a2a.trusted_keys, TrustedKey(kid=signing.kid, jwk=signing.jwk))
        settings = settings.model_copy(
            update={"a2a": settings.a2a.model_copy(update={"trusted_keys": trusted})}
        )
    except MissingExtraError:
        signing = None  # without the a2a extra the tour skips the agent

    steps: list[tuple[str, bool, str]] = []

    def step(key: str, ok: bool, **values: object) -> None:
        steps.append((t.text(f"demo.tour.{key}.title"), ok, t.text(f"demo.tour.{key}", **values)))

    app = create_app(settings, mcp_transport=world.transport(), a2a_transport=world.transport())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://arbiter.demo"
        ) as client,
    ):
        runtime, compliance = app.state.runtime, app.state.compliance
        async with runtime.database.transaction() as session:
            tenant = await ensure_tenant(session, slug=DEMO_TENANT, name="Demo")
            reviewer = await reviewer_for(session, tenant.id, DEMO_REVIEWER)
            results = [
                await run_scenario(
                    session, tenant.id, compliance, load_scenario(name), reviewer_id=reviewer
                )
                for name in packaged_scenarios()
            ]
            # The tour's own systems: its traffic must not land on a scenario's system.
            tour_systems = parse_declarations(
                resources.files("ai_arbiter")
                .joinpath("scenarios", "tour", "systems.yaml")
                .read_text(encoding="utf-8"),
                origin="tour",
            )
            for declaration in tour_systems:
                declared = await compliance.inventory.declare(session, tenant.id, declaration)
                await compliance.classifier.classify_system(session, declared.system)
            teams = {
                team.name: team for team in await runtime.identity.list_teams(session, tenant.id)
            }
            team = teams.get("demo-tour") or await runtime.identity.create_team(
                session, tenant.id, "demo-tour"
            )
            projects = {
                (project.team_id, project.name): project
                for project in await runtime.identity.list_projects(session, tenant.id)
            }
            project = projects.get((team.id, "tour")) or await runtime.identity.create_project(
                session, tenant.id, team.id, "tour"
            )
            for role in (AccessRole.ADMIN, AccessRole.DEVELOPER):
                await runtime.identity.grant_role(
                    session, tenant.id, principal_id=reviewer, role=role
                )

            async def key_for(system: str | None) -> tuple[dict[str, str], str | None]:
                system_id = None
                if system is not None:
                    system_id = (await compliance.inventory.get(session, tenant.id, system)).id
                _, value = await runtime.identity.issue_api_key(
                    session,
                    tenant.id,
                    project_id=project.id,
                    principal_id=reviewer,
                    name=f"demo tour {system or 'admin'}",
                    ai_system_id=system_id,
                )
                return {"Authorization": f"Bearer {value}"}, str(system_id) if system_id else None

            admin, _ = await key_for(None)
            worker, worker_system = await key_for("tour-office-assistant")
            forbidden, _ = await key_for("tour-mood-monitor")
        systems = sum(len(result.systems) for result in results) + len(tour_systems)
        step("inventory", all(result.as_expected for result in results), systems=systems)

        chat = {
            "model": "mock-small",
            "messages": [
                {"role": "user", "content": "Remind mario.rossi@example.com about the invoice."}
            ],
        }
        answered = await client.post("/v1/chat/completions", json=chat, headers=worker)
        redacted = answered.headers.get("x-arbiter-redacted", "")
        step(
            "redaction", answered.status_code == 200 and "email" in redacted, found=redacted or "-"
        )

        denied = await client.post("/v1/chat/completions", json=chat, headers=forbidden)
        reasons = denied.json().get("reasons") or [{}]
        rule = str(reasons[0].get("rule_id", "-"))
        step("prohibited", denied.status_code == 403, rule=rule)

        await client.post(
            "/api/v1/mcp/servers",
            json={
                "key": "demo-files",
                "name": "Demo file tools",
                "url": DEMO_MCP_URL,
                "ai_system": "tour-office-assistant",
            },
            headers=admin,
        )
        found = await client.post("/api/v1/mcp/servers/demo-files/discovery", headers=admin)
        await client.post(
            "/api/v1/mcp/servers/demo-files/grants",
            json={"scope_type": "ai_system", "scope_id": worker_system, "tool": "read"},
            headers=admin,
        )
        body, headers = mcp_request("tools/call", "read")
        allowed = await client.post("/mcp/demo-files", content=body, headers={**headers, **worker})
        body, headers = mcp_request("tools/call", "write")
        refused = await client.post("/mcp/demo-files", content=body, headers={**headers, **worker})
        refused_rule = ", ".join(
            (refused.json().get("error") or {}).get("data", {}).get("rules", ["-"])
        )
        step(
            "mcp",
            (found.status_code, allowed.status_code, refused.status_code) == (200, 200, 403),
            tools=", ".join(found.json().get("tools", [])) if found.status_code == 200 else "-",
            rule=refused_rule,
        )

        if signing is None:
            steps.append((t.text("demo.tour.agent.title"), True, t.text("demo.tour.agent_skipped")))
        else:
            await client.post(
                "/api/v1/a2a/agents",
                json={
                    "key": "demo-routes",
                    "name": "Demo route planner",
                    "card_url": DEMO_CARD_URL,
                    "ai_system": "tour-office-assistant",
                },
                headers=admin,
            )
            first = await client.post("/api/v1/a2a/agents/demo-routes/card", headers=admin)
            await client.post(
                "/api/v1/a2a/agents/demo-routes/grants",
                json={"scope_type": "ai_system", "scope_id": worker_system},
                headers=admin,
            )
            message = {"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {}}
            rpc_headers = {"content-type": "application/json", "a2a-version": "1.0", **worker}
            sent = await client.post("/a2a/demo-routes", json=message, headers=rpc_headers)
            # Someone changes the card after it was signed.
            world.card = json.dumps({**json.loads(world.card), "version": "6.6.6"}).encode()
            second = await client.post("/api/v1/a2a/agents/demo-routes/card", headers=admin)
            blocked = await client.post("/a2a/demo-routes", json=message, headers=rpc_headers)
            blocked_rule = ", ".join(
                (blocked.json().get("error") or {}).get("data", {}).get("rules", ["-"])
            )
            world.card = signing.sign(DEMO_CARD)
            await client.post("/api/v1/a2a/agents/demo-routes/card", headers=admin)
            step(
                "agent",
                (sent.status_code, blocked.status_code) == (200, 403)
                and first.json().get("verification") == "verified"
                and second.json().get("verification") == "invalid",
                before=str(first.json().get("verification")),
                after=str(second.json().get("verification")),
                rule=blocked_rule,
            )

        scanned = await client.post("/api/v1/scans", headers=admin)
        findings = await client.get("/api/v1/findings", headers=admin)
        step(
            "scan",
            scanned.is_success and findings.status_code == 200,
            findings=len(findings.json()) if findings.status_code == 200 else 0,
        )

        verified = await client.get("/api/v1/audit/verify", headers=admin)
        chain = verified.json()
        step("audit", bool(chain.get("ok")), entries=chain.get("entries", 0))
    return steps


@app.command("tour")
def tour(
    ctx: typer.Context,
    case: Annotated[
        str,
        typer.Option(
            "--case",
            help="Which demonstration: general, or consulting (an IT consulting firm).",
        ),
    ] = "general",
    locale: Locale = "en",
) -> None:
    """A guided demonstration in one command: the gateway and the toolkit at work.

    ``general`` loads the scenarios into the tenant ``demo``, sends requests through the
    gateway with a mock model, calls a mock MCP server and a mock agent through the
    proxies, then scans and verifies the audit log. ``consulting`` follows an invented IT
    consulting firm with its own internal regulation, in the tenant ``demo-consulting``.
    Everything runs in this process: no network, no real model, and no other tenant is
    touched.
    """
    t = translator(locale)
    if case not in CASES:
        raise fail(ArbiterError(f"unknown case '{case}': use {' or '.join(CASES)}"))
    settings = settings_from(ctx)
    # The demonstration makes dozens of requests inside this process: one log line for
    # each would bury the steps it prints.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if case == "consulting":
        steps, tenant = run(consulting_tour(settings, t)), CONSULTING_TENANT
        typer.echo(t.text("demo.consulting.intro"))
    else:
        steps, tenant = run(_tour(settings, t)), DEMO_TENANT
        typer.echo(t.text("demo.tour.intro"))
    typer.echo("")
    for number, (title, ok, detail) in enumerate(steps, start=1):
        mark = t.text("demo.as_expected") if ok else t.text("demo.differs")
        typer.echo(f"{number}. {title}  [{mark}]")
        typer.echo(f"   {detail}")
    typer.echo("")
    typer.echo(t.text("demo.next", tenant=tenant))
    typer.echo(t.text("demo.invented"))
    typer.echo(t.text("disclaimer"))
    if not all(ok for _, ok, _ in steps):
        raise fail(ArbiterError(t.text("demo.mismatch")))
