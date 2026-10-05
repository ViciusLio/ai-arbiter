"""The guided demonstration for an IT consulting firm: ``arbiter demo tour --case consulting``.

An invented firm that works by engagement approved one family of models and declares the
tools its people reach those models through. The demonstration declares them, applies the
firm's internal regulation as a policy pack on top of the default one, and then acts as
the firm's people would: every step is a request through the gateway or its MCP proxy, in
this process, with stand-ins for the model and for the tool server (ADR-0056, ADR-0060).

The run is returned as data, so that it can be printed step by step or written as a page
to show (``demo_report``).
"""

from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from ai_arbiter.cli.common import reviewer_for
from ai_arbiter.compliance.inventory.declarations import parse_declarations
from ai_arbiter.core.config.settings import DeploymentSettings, Settings
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.errors import MissingExtraError
from ai_arbiter.core.i18n import Translator
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.tenant import ensure_tenant

# Its own tenant: the digest and the reports of the firm hold nothing of the scenarios.
CONSULTING_TENANT = "demo-consulting"
FIRM = "Nordwind Consulting (invented)"
REVIEWER = "AI committee of the demo"
_FILES = ("scenarios", "consulting")

# The indicative tier the demonstration expects of each declared system.
EXPECTED_TIERS = {
    "claude-assistant": "transparency",
    "kiro-ide": "minimal",
    "github-copilot": "minimal",
    "cv-screening": "high_risk",
    "meeting-mood-analyser": "prohibited",
}
# The one family of models the firm approved, and two engines the same tools could use.
SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-4-5"
APPROVED_MODELS = (SONNET, HAIKU)
OTHER_ENGINES = ("gpt-4o", "gemini-2.5-pro")
REPOSITORY_TOOLS = ("read_file", "open_pull_request", "delete_branch")
GRANTED_TOOL = "read_file"
TEAM = "nordwind"
# Engagements and departments, as projects of the gateway.
BANK, RETAIL, STAFF, HR, LAB = "client-bank", "client-retail", "staff", "hr", "lab"


@dataclass(frozen=True)
class DemoStep:
    key: str
    title: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ToolUse:
    """What one tool asked of one model: how many requests went through, how many did not."""

    tool: str
    model: str
    approved: bool
    allowed: int
    denied: int


@dataclass(frozen=True)
class DemoRun:
    """A run of the demonstration: its steps, and what the firm's tenant holds after it."""

    steps: tuple[DemoStep, ...]
    firm: str = FIRM
    tenant: str = CONSULTING_TENANT
    generated_at: datetime = field(default_factory=utcnow)
    pack_version: str = ""
    approved_models: tuple[str, ...] = APPROVED_MODELS
    # Each system as the API returns it, in the language of the run.
    systems: tuple[dict[str, Any], ...] = ()
    usage: tuple[ToolUse, ...] = ()
    findings: tuple[dict[str, Any], ...] = ()
    candidates: tuple[str, ...] = ()
    audit_entries: int = 0
    audit_head: str = ""

    @property
    def as_expected(self) -> bool:
        return all(step.ok for step in self.steps)


def _chat(text: str, model: str = SONNET) -> dict[str, Any]:
    return {"model": model, "messages": [{"role": "user", "content": text}]}


def _rule(response: Any) -> str:
    """The rule that refused a chat request, as the gateway names it."""
    reasons = response.json().get("reasons") or []
    denying = [str(reason.get("rule_id")) for reason in reasons if reason.get("outcome") == "deny"]
    return ", ".join(denying) or "-"


def _demo_settings(settings: Settings, pack: Any) -> Settings:
    """The workspace's settings with the firm's regulation and its one approved deployment."""
    claude = DeploymentSettings(
        name="claude",
        provider="mock",
        model=SONNET,
        serves=APPROVED_MODELS,
        region="local",
        priced_as="mock-small",
    )
    return settings.model_copy(
        update={
            "deployments": (claude,),
            "policy": settings.policy.model_copy(
                update={"pack": pack, "allowed_models": APPROVED_MODELS}
            ),
        }
    )


async def consulting_tour(settings: Settings, t: Translator) -> DemoRun:
    """Walk through a day of the firm, and return what happened. Safe to repeat."""
    try:
        import httpx

        from ai_arbiter.gateway.api.app import create_app
    except ImportError as exc:
        raise MissingExtraError("gateway", "The guided demonstration") from exc
    from ai_arbiter.adapters.mock.tools import DEMO_MCP_URL, MockToolWorld, mcp_request

    files = resources.files("ai_arbiter").joinpath(*_FILES)
    steps: list[DemoStep] = []

    def step(key: str, ok: bool, **values: object) -> None:
        steps.append(
            DemoStep(
                key,
                t.text(f"demo.consulting.{key}.title"),
                ok,
                t.text(f"demo.consulting.{key}", **values),
            )
        )

    world = MockToolWorld(tools=REPOSITORY_TOOLS)
    with ExitStack() as stack:
        pack = stack.enter_context(resources.as_file(files.joinpath("policy.yaml")))
        app = create_app(_demo_settings(settings, pack), mcp_transport=world.transport())
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
                names: dict[UUID, str] = {}
                for declaration in declarations:
                    declared = await compliance.inventory.declare(session, tenant.id, declaration)
                    await compliance.classifier.classify_system(session, declared.system)
                    system_ids[declaration.key] = declared.system.id
                    names[declared.system.id] = declaration.name
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
                    for name in (BANK, RETAIL, STAFF, HR, LAB)
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
                kiro = await key_for(BANK, "kiro-ide")
                copilot = await key_for(BANK, "github-copilot")
                sales = await key_for(RETAIL, "claude-assistant")
                recruiter = await key_for(HR, "cv-screening")
                mood = await key_for(HR, "meeting-mood-analyser")
                experimenter = await key_for(LAB, None)
            locale = {"Accept-Language": t.locale}

            async def ask(key: dict[str, str], text: str, model: str = SONNET) -> Any:
                return await client.post(
                    "/v1/chat/completions", json=_chat(text, model), headers={**key, **locale}
                )

            # 1. What the firm declared, and the indicative tier of each system.
            listed = await client.get("/api/v1/systems", headers={**admin, **locale})
            tiers = {
                item["key"]: (item.get("classification") or {}).get("engine_tier")
                for item in (listed.json() if listed.status_code == 200 else [])
            }
            step(
                "inventory",
                tiers == EXPECTED_TIERS,
                count=len(tiers),
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

            # 3. Kiro on the approved engine, with personal data of the client's customers.
            asked = await ask(
                kiro,
                "Why does the transfer of anna.bianchi@example.com to "
                "IT60X0542811101000000123456 fail in this function?",
            )
            masked = asked.headers.get("x-arbiter-redacted", "")
            step(
                "approved_engine",
                asked.status_code == 200 and {"email", "iban"} <= set(masked.split(",")),
                model=SONNET,
                found=masked.replace(",", ", ") or "-",
            )

            # 4. The same tool, switched to another engine.
            switched = await ask(kiro, "Refactor this module.", OTHER_ENGINES[0])
            step(
                "other_engine",
                switched.status_code == 403,
                model=OTHER_ENGINES[0],
                rule=_rule(switched),
            )

            # 5. The rule is about the model, not about the tool: Copilot too.
            with_claude = await ask(copilot, "Complete this unit test.")
            with_other = await ask(copilot, "Complete this unit test.", OTHER_ENGINES[1])
            step(
                "second_tool",
                (with_claude.status_code, with_other.status_code) == (200, 403),
                allowed=SONNET,
                denied=OTHER_ENGINES[1],
                rule=_rule(with_other),
            )

            # 6. A consultant pastes a token of the client's repository.
            token = "gh" + "p_" + "Demo" * 9  # shaped like a token, and not one
            leaked = await ask(kiro, f"The pipeline fails with the token {token}, what is wrong?")
            step("credential", leaked.status_code == 403, rule=_rule(leaked))

            # 7. A high-risk system waits for a person, then works.
            screening = "Rank these three applications for the analyst position."
            current = await client.get("/api/v1/systems/cv-screening", headers=admin)
            status = (current.json().get("classification") or {}).get("status")
            if status == "proposed":
                before = await ask(recruiter, screening)
                reviewed = await client.post(
                    "/api/v1/systems/cv-screening/review",
                    json={"decision": "confirmed"},
                    headers=admin,
                )
                after = await ask(recruiter, screening)
                step(
                    "high_risk",
                    (before.status_code, reviewed.status_code, after.status_code)
                    == (403, 200, 200),
                    rule=_rule(before),
                )
            else:
                again = await ask(recruiter, screening)
                step("high_risk_repeated", again.status_code == 200)

            # 8. A practice the AI Act prohibits, even on the approved model.
            refused = await ask(mood, "How did the team feel in the meeting of this morning?")
            step("prohibited", refused.status_code == 403, rule=_rule(refused), model=SONNET)

            # 9. The budget of an engagement.
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
            offer = "Draft the summary of the offer for the loyalty programme."
            spent = [await ask(sales, offer, HAIKU) for _ in range(2)]
            step(
                "budget",
                spent[-1].status_code == 403 and "POL-BUDGET-EXCEEDED" in _rule(spent[-1]),
                rule=_rule(spent[-1]) if spent[-1].status_code == 403 else "-",
                project=RETAIL,
            )

            # 10. Tools on the client's repository: only what a grant names.
            await client.post(
                "/api/v1/mcp/servers",
                json={
                    "key": "client-repository",
                    "name": "Repository of the client",
                    "url": DEMO_MCP_URL,
                    "ai_system": "kiro-ide",
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
                    "scope_id": str(system_ids["kiro-ide"]),
                    "tool": GRANTED_TOOL,
                },
                headers=admin,
            )

            async def tool(method: str, name: str | None = None) -> Any:
                body, headers = mcp_request(method, name)
                return await client.post(
                    "/mcp/client-repository", content=body, headers={**headers, **kiro}
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

            # 11. Someone uses the approved model with no declared tool behind the request.
            for _ in range(3):
                await ask(experimenter, "Classify these support tickets by urgency.")
            scanned = await client.post("/api/v1/scans", headers=admin)
            candidates = await client.get("/api/v1/candidates", headers=admin)
            named = [
                str(item.get("project"))
                for item in (candidates.json().get("candidates") or [])
                if candidates.status_code == 200
            ]
            step(
                "shadow",
                scanned.is_success and any(name.endswith(LAB) for name in named),
                names=", ".join(named) or "-",
            )

            # 12. What the firm has to look at.
            findings = await client.get("/api/v1/findings", headers={**admin, **locale})
            open_findings = findings.json() if findings.status_code == 200 else []
            step(
                "findings",
                findings.status_code == 200 and len(open_findings) > 0,
                findings=len(open_findings),
            )

            # 13. The record of it all.
            verified = await client.get("/api/v1/audit/verify", headers=admin)
            chain = verified.json()
            step("audit", bool(chain.get("ok")), entries=chain.get("entries", 0))

            after_run = await client.get("/api/v1/systems", headers={**admin, **locale})
            pack_version = runtime.policy.pack.version
            undeclared = t.text("demo.report.undeclared")
            totals: dict[tuple[str, str], list[int]] = {}
            async with runtime.database.session() as session:
                counted = await session.execute(
                    select(
                        Interaction.ai_system_id,
                        Interaction.requested_model,
                        Interaction.status,
                        func.count(),
                    )
                    .where(Interaction.tenant_id == tenant.id)
                    .group_by(
                        Interaction.ai_system_id, Interaction.requested_model, Interaction.status
                    )
                )
                for system_id, model, outcome, count in counted:
                    tool_name = names.get(system_id, undeclared) if system_id else undeclared
                    cell = totals.setdefault((tool_name, str(model)), [0, 0])
                    cell[0 if outcome == "ok" else 1] += int(count)
    usage = tuple(
        ToolUse(tool_name, model, model in APPROVED_MODELS, allowed, denied)
        for (tool_name, model), (allowed, denied) in sorted(totals.items())
    )
    severity = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    by_id = {str(identifier): name for identifier, name in names.items()}
    return DemoRun(
        steps=tuple(steps),
        pack_version=pack_version,
        systems=tuple(after_run.json() if after_run.status_code == 200 else []),
        usage=usage,
        findings=tuple(
            {**item, "system": by_id.get(str(item.get("ai_system_id")), "")}
            for item in sorted(
                open_findings, key=lambda item: severity.get(str(item.get("severity")), 9)
            )
        ),
        candidates=tuple(named),
        audit_entries=int(chain.get("entries", 0)),
        audit_head=str(chain.get("head_hash") or ""),
    )
