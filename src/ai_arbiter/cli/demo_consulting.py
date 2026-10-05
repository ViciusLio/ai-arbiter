"""The guided demonstration for an IT consulting firm: ``arbiter demo tour --case consulting``.

An invented firm that works by engagement uses several AI tools. The demonstration
declares them, applies the firm's internal regulation as a policy pack on top of the
default one, and then acts as the firm's people would: every step is a request through
the gateway or its MCP proxy, in this process, with stand-ins for the model and for the
tool server (ADR-0056).
"""

from contextlib import ExitStack
from importlib import resources
from typing import Any
from uuid import UUID

from ai_arbiter.cli.common import reviewer_for
from ai_arbiter.compliance.inventory.declarations import parse_declarations
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.errors import MissingExtraError
from ai_arbiter.core.i18n import Translator
from ai_arbiter.core.persistence.tenant import ensure_tenant

# Its own tenant: the digest and the reports of the firm hold nothing of the scenarios.
CONSULTING_TENANT = "demo-consulting"
FIRM = "Nordwind Consulting (invented)"
REVIEWER = "AI committee of the demo"
_FILES = ("scenarios", "consulting")

# The indicative tier the demonstration expects of each declared system.
EXPECTED_TIERS = {
    "code-assistant": "minimal",
    "proposal-writer": "transparency",
    "cv-screening": "high_risk",
    "meeting-mood-analyser": "prohibited",
}
APPROVED_MODELS = ("mock-small",)
REPOSITORY_TOOLS = ("read_file", "open_pull_request", "delete_branch")
GRANTED_TOOL = "read_file"
TEAM = "nordwind"
# Engagements and departments, as projects of the gateway.
BANK, RETAIL, HR, LAB = "client-bank", "client-retail", "hr", "lab"

Step = tuple[str, bool, str]


def _chat(text: str, model: str = "mock-small") -> dict[str, Any]:
    return {"model": model, "messages": [{"role": "user", "content": text}]}


def _rule(response: Any) -> str:
    """The rule that refused a chat request, as the gateway names it."""
    reasons = response.json().get("reasons") or []
    denying = [str(reason.get("rule_id")) for reason in reasons if reason.get("outcome") == "deny"]
    return ", ".join(denying) or "-"


async def consulting_tour(settings: Settings, t: Translator) -> list[Step]:
    """Walk through a day of the firm. Returns, for each step, its title, whether it
    went as the demonstration expects, and what was observed. Safe to repeat.
    """
    try:
        import httpx

        from ai_arbiter.gateway.api.app import create_app
    except ImportError as exc:
        raise MissingExtraError("gateway", "The guided demonstration") from exc
    from ai_arbiter.adapters.mock.tools import DEMO_MCP_URL, MockToolWorld, mcp_request

    files = resources.files("ai_arbiter").joinpath(*_FILES)
    steps: list[Step] = []

    def step(key: str, ok: bool, **values: object) -> None:
        steps.append(
            (
                t.text(f"demo.consulting.{key}.title"),
                ok,
                t.text(f"demo.consulting.{key}", **values),
            )
        )

    world = MockToolWorld(tools=REPOSITORY_TOOLS)
    with ExitStack() as stack:
        pack = stack.enter_context(resources.as_file(files.joinpath("policy.yaml")))
        settings = settings.model_copy(
            update={
                "policy": settings.policy.model_copy(
                    update={"pack": pack, "allowed_models": APPROVED_MODELS}
                )
            }
        )
        app = create_app(settings, mcp_transport=world.transport())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://arbiter.demo"
            ) as client,
        ):
            runtime, compliance = app.state.runtime, app.state.compliance
            identity = runtime.identity
            async with runtime.database.transaction() as session:
                tenant = await ensure_tenant(session, slug=CONSULTING_TENANT, name=FIRM)
                reviewer = await reviewer_for(session, tenant.id, REVIEWER)
                declarations = parse_declarations(
                    files.joinpath("systems.yaml").read_text(encoding="utf-8"),
                    origin="consulting",
                )
                system_ids: dict[str, UUID] = {}
                for declaration in declarations:
                    declared = await compliance.inventory.declare(session, tenant.id, declaration)
                    await compliance.classifier.classify_system(session, declared.system)
                    system_ids[declaration.key] = declared.system.id
                teams = {team.name: team for team in await identity.list_teams(session, tenant.id)}
                team = teams.get(TEAM) or await identity.create_team(session, tenant.id, TEAM)
                existing = {
                    project.name: project
                    for project in await identity.list_projects(session, tenant.id)
                    if project.team_id == team.id
                }
                projects = {
                    name: existing.get(name)
                    or await identity.create_project(session, tenant.id, team.id, name)
                    for name in (BANK, RETAIL, HR, LAB)
                }
                for role in (AccessRole.ADMIN, AccessRole.DEVELOPER):
                    await identity.grant_role(session, tenant.id, principal_id=reviewer, role=role)

                async def key_for(project: str, system: str | None) -> dict[str, str]:
                    _, value = await identity.issue_api_key(
                        session,
                        tenant.id,
                        project_id=projects[project].id,
                        principal_id=reviewer,
                        name=f"consulting demo {system or project}",
                        ai_system_id=system_ids[system] if system is not None else None,
                    )
                    return {"Authorization": f"Bearer {value}"}

                admin = await key_for(HR, None)
                coder = await key_for(BANK, "code-assistant")
                writer = await key_for(RETAIL, "proposal-writer")
                recruiter = await key_for(HR, "cv-screening")
                mood = await key_for(HR, "meeting-mood-analyser")
                experimenter = await key_for(LAB, None)

            # 1. What the firm declared, and the indicative tier of each system.
            listed = await client.get("/api/v1/systems", headers=admin)
            tiers = {
                item["key"]: (item.get("classification") or {}).get("engine_tier")
                for item in (listed.json() if listed.status_code == 200 else [])
            }
            step(
                "inventory",
                tiers == EXPECTED_TIERS,
                tiers="; ".join(
                    f"{key}: {t.text('tier.' + str(tier))}" for key, tier in sorted(tiers.items())
                )
                or "-",
            )

            # 2. The internal regulation is data, loaded on top of the default policy.
            own = [rule.id for rule in runtime.policy.pack.rules if rule.id.startswith("IR-")]
            step(
                "regulation",
                len(own) == 2,
                version=runtime.policy.pack.version,
                rules=", ".join(own) or "-",
                models=", ".join(APPROVED_MODELS),
            )

            # 3. A consultant pastes personal data of the client's customers.
            asked = await client.post(
                "/v1/chat/completions",
                json=_chat(
                    "Why does the transfer of anna.bianchi@example.com to "
                    "IT60X0542811101000000123456 fail in this function?"
                ),
                headers=coder,
            )
            masked = asked.headers.get("x-arbiter-redacted", "")
            step(
                "redaction",
                asked.status_code == 200 and {"email", "iban"} <= set(masked.split(",")),
                found=masked.replace(",", ", ") or "-",
            )

            # 4. The same consultant pastes a token of the client's repository.
            token = "gh" + "p_" + "Demo" * 9  # shaped like a token, and not one
            leaked = await client.post(
                "/v1/chat/completions",
                json=_chat(f"The pipeline fails with the token {token}, what is wrong?"),
                headers=coder,
            )
            step("credential", leaked.status_code == 403, rule=_rule(leaked))

            # 5. A model the firm did not approve.
            other = await client.post(
                "/v1/chat/completions",
                json=_chat("Summarise the kick-off notes.", model="mock-large"),
                headers=coder,
            )
            step("model", other.status_code == 403, rule=_rule(other), model="mock-large")

            # 6. A high-risk system waits for a person, then works.
            screening = _chat("Rank these three applications for the analyst position.")
            current = await client.get("/api/v1/systems/cv-screening", headers=admin)
            status = (current.json().get("classification") or {}).get("status")
            if status == "proposed":
                before = await client.post(
                    "/v1/chat/completions", json=screening, headers=recruiter
                )
                reviewed = await client.post(
                    "/api/v1/systems/cv-screening/review",
                    json={"decision": "confirmed"},
                    headers=admin,
                )
                after = await client.post("/v1/chat/completions", json=screening, headers=recruiter)
                step(
                    "high_risk",
                    (before.status_code, reviewed.status_code, after.status_code)
                    == (403, 200, 200),
                    rule=_rule(before),
                )
            else:
                again = await client.post("/v1/chat/completions", json=screening, headers=recruiter)
                step("high_risk_repeated", again.status_code == 200)

            # 7. A practice the AI Act prohibits.
            refused = await client.post(
                "/v1/chat/completions",
                json=_chat("How did the team feel in the meeting of this morning?"),
                headers=mood,
            )
            step("prohibited", refused.status_code == 403, rule=_rule(refused))

            # 8. The budget of an engagement.
            retail = str(projects[RETAIL].id)
            budgets = await client.get("/api/v1/budgets", headers=admin)
            if not any(item["scope_id"] == retail for item in budgets.json()):
                await client.post(
                    "/api/v1/budgets",
                    json={
                        "scope_type": "project",
                        "scope_id": retail,
                        "period": "month",
                        "limit_amount": "0.000001",
                        "hard": True,
                    },
                    headers=admin,
                )
            offer = _chat("Draft the summary of the offer for the loyalty programme.")
            spent = [
                await client.post("/v1/chat/completions", json=offer, headers=writer)
                for _ in range(2)
            ]
            step(
                "budget",
                spent[-1].status_code == 403 and "POL-BUDGET-EXCEEDED" in _rule(spent[-1]),
                rule=_rule(spent[-1]) if spent[-1].status_code == 403 else "-",
                project=RETAIL,
            )

            # 9. Tools on the client's repository: only what a grant names.
            await client.post(
                "/api/v1/mcp/servers",
                json={
                    "key": "client-repository",
                    "name": "Repository of the client",
                    "url": DEMO_MCP_URL,
                    "ai_system": "code-assistant",
                },
                headers=admin,
            )
            found = await client.post(
                "/api/v1/mcp/servers/client-repository/discovery", headers=admin
            )
            await client.post(
                "/api/v1/mcp/servers/client-repository/grants",
                json={
                    "scope_type": "ai_system",
                    "scope_id": str(system_ids["code-assistant"]),
                    "tool": GRANTED_TOOL,
                },
                headers=admin,
            )

            async def tool(method: str, name: str | None = None) -> Any:
                body, headers = mcp_request(method, name)
                return await client.post(
                    "/mcp/client-repository", content=body, headers={**headers, **coder}
                )

            shown = await tool("tools/list")
            visible = [
                item.get("name")
                for item in (shown.json().get("result") or {}).get("tools", [])
                if shown.status_code == 200
            ]
            read = await tool("tools/call", GRANTED_TOOL)
            delete = await tool("tools/call", "delete_branch")
            step(
                "tools",
                found.status_code == 200
                and visible == [GRANTED_TOOL]
                and (read.status_code, delete.status_code) == (200, 403),
                offered=", ".join(REPOSITORY_TOOLS),
                visible=", ".join(str(name) for name in visible) or "-",
                rule=", ".join(
                    (delete.json().get("error") or {}).get("data", {}).get("rules", ["-"])
                ),
            )

            # 10. Someone tries a model with no declared system behind the request.
            for _ in range(3):
                await client.post(
                    "/v1/chat/completions",
                    json=_chat("Classify these support tickets by urgency."),
                    headers=experimenter,
                )
            scanned = await client.post("/api/v1/scans", headers=admin)
            candidates = await client.get("/api/v1/candidates", headers=admin)
            named = [
                str(item.get("project"))
                for item in (candidates.json().get("candidates") or [])
                if candidates.status_code == 200
            ]
            findings = await client.get("/api/v1/findings", headers=admin)
            step(
                "shadow",
                scanned.is_success and any(name.endswith(LAB) for name in named),
                names=", ".join(named) or "-",
                findings=len(findings.json()) if findings.status_code == 200 else 0,
            )

            # 11. The record of it all.
            verified = await client.get("/api/v1/audit/verify", headers=admin)
            chain = verified.json()
            step("audit", bool(chain.get("ok")), entries=chain.get("entries", 0))
    return steps
