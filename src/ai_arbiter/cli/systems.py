"""``arbiter systems``: declare AI systems, classify them, review the classification."""

from pathlib import Path
from typing import Annotated

import typer

from ai_arbiter.cli.common import (
    DISCLAIMER,
    compliance_for,
    fail,
    open_database,
    reviewer_for,
    run,
    settings_from,
    tenant_id_for,
)
from ai_arbiter.compliance.classifier.model import ReviewDecision
from ai_arbiter.compliance.classifier.service import EffectiveClassification
from ai_arbiter.compliance.inventory.declarations import load_declarations
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.i18n import SUPPORTED_LOCALES, Translator

app = typer.Typer(help="Declare, classify and review AI systems.", no_args_is_help=True)

TenantSlug = Annotated[str, typer.Option("--tenant", help="Tenant slug.")]
Locale = Annotated[str, typer.Option("--locale", help="Language: en or it.")]


def translator(locale: str) -> Translator:
    if locale not in SUPPORTED_LOCALES:
        raise fail(
            ArbiterError(f"unsupported locale '{locale}': use {' or '.join(SUPPORTED_LOCALES)}")
        )
    return Translator(locale)


def _line(key: str, current: EffectiveClassification | None, name: str, t: Translator) -> str:
    tier = t.text(f"tier.{current.tier.value}") if current else t.text("tier.not_classified")
    status = t.text(f"review.{current.status}") if current else "-"
    return f"{key:<32} {tier:<26} {status:<32} {name}"


async def _apply(
    settings: Settings, tenant: str, path: Path, classify: bool
) -> list[tuple[str, str, str]]:
    declarations = load_declarations(path)
    compliance = compliance_for(settings)
    rows: list[tuple[str, str, str]] = []
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            for declaration in declarations:
                declared = await compliance.inventory.declare(session, tenant_id, declaration)
                tier = "-"
                if classify:
                    current, _ = await compliance.classifier.classify_system(
                        session, declared.system
                    )
                    tier = current.tier.value
                rows.append((declaration.key, declared.change, tier))
    return rows


@app.command("apply")
def apply(
    ctx: typer.Context,
    file: Annotated[Path, typer.Option("--file", "-f", help="Declaration file (YAML).")],
    classify: Annotated[
        bool,
        typer.Option("--classify/--no-classify", help="Classify each system after declaring it."),
    ] = True,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Create or update the systems of a declaration file. Safe to run again."""
    rows = run(_apply(settings_from(ctx), tenant, file, classify))
    for key, change, tier in rows:
        typer.echo(f"{key:<32} {change:<10} {tier}")
    typer.echo("")
    typer.echo(
        "Classifications are indicative until a person reviews them: arbiter systems show KEY"
    )


async def _list(settings: Settings, tenant: str, locale: str) -> list[str]:
    t = translator(locale)
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            return [
                _line(
                    system.key,
                    await compliance.classifier.current(session, tenant_id, system.id),
                    system.name,
                    t,
                )
                for system in await compliance.inventory.list(session, tenant_id)
            ]


@app.command("list")
def list_systems(
    ctx: typer.Context, tenant: TenantSlug = LOCAL_TENANT_SLUG, locale: Locale = "en"
) -> None:
    """List declared systems with their indicative tier and review state."""
    lines = run(_list(settings_from(ctx), tenant, locale))
    if not lines:
        typer.echo("No AI system is declared. Start with: arbiter systems apply -f FILE")
        return
    for line in lines:
        typer.echo(line)


async def _show(settings: Settings, tenant: str, key: str, locale: str) -> list[str]:
    t = translator(locale)
    compliance = compliance_for(settings)
    today = utcnow().date()
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            system = await compliance.inventory.get(session, tenant_id, key)
            roles = await compliance.inventory.roles(session, system)
            current = await compliance.classifier.current(session, tenant_id, system.id)
    out = [
        f"{system.name} ({system.key})",
        f"  lifecycle: {system.lifecycle}",
        f"  roles:     {', '.join(role.role for role in roles) or '-'}",
    ]
    if system.purpose:
        out.append(f"  purpose:   {system.purpose}")
    if current is None:
        return [*out, "", t.text("scan.system_not_classified"), "", t.text("disclaimer")]
    classification = current.classification
    out += [
        "",
        f"{t.text('digest.column.tier')}: {t.text('tier.' + current.tier.value)}",
        f"{t.text('digest.column.review')}: {t.text('review.' + current.status)}",
        f"{t.text('digest.rule_pack')}: "
        f"{classification.rulepack} {classification.rulepack_version}",
    ]
    if current.review is not None and current.review.reason:
        out.append(f"  reason: {current.review.reason}")
    if current.review is not None and current.review.tier != classification.tier:
        out.append(f"  engine: {t.text('tier.' + classification.tier)}")
    if classification.obligations:
        out.append("")
        for item in classification.obligations:
            applies = item.get("applies_from")
            when = ""
            if applies:
                pending = applies > today.isoformat()
                when = f" [{applies}{', ' + t.text('digest.readiness') if pending else ''}]"
            addressed = (
                ""
                if item.get("applies_to_declared_roles")
                else f" (for: {', '.join(item.get('roles') or [])})"
            )
            refs = ", ".join(item.get("legal_refs") or [])
            out.append(f"  - {t.text(item['message_key'])} ({refs}){when}{addressed}")
    if classification.missing_facts:
        out += [
            "",
            f"{len(classification.missing_facts)} unanswered questions: "
            f"arbiter systems questions {key}",
        ]
    if (
        compliance.ai_act_pack.regulation
        and compliance.ai_act_pack.regulation.review != "confirmed"
    ):
        out += ["", t.text("digest.review_pending_note")]
    return [*out, "", t.text("digest.indicative_note"), t.text("disclaimer")]


@app.command("show")
def show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="System key.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
    locale: Locale = "en",
) -> None:
    """Show a system: indicative tier, review state, obligations with their provisions."""
    for line in run(_show(settings_from(ctx), tenant, key, locale)):
        typer.echo(line)


async def _questions(settings: Settings, tenant: str, key: str, locale: str) -> list[str]:
    t = translator(locale)
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            system = await compliance.inventory.get(session, tenant_id, key)
            result = await compliance.classifier.evaluate(session, system)
    names = compliance.classifier.questions(result)
    if not names:
        return ["Every question that could change the result is answered."]
    out = [f"{len(names)} questions to answer under 'facts' of '{key}' (true or false):", ""]
    for name in names:
        spec = compliance.ai_act_pack.facts[name]
        out += [f"  # {t.text('fact.' + name)} ({spec.ref})", f"  {name}:", ""]
    out.append(
        "Answering may open further questions: details are asked only where an area applies."
    )
    return out


@app.command("questions")
def questions(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="System key.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
    locale: Locale = "en",
) -> None:
    """List the questions still to answer for a system, ready to paste into its declaration."""
    for line in run(_questions(settings_from(ctx), tenant, key, locale)):
        typer.echo(line)


@app.command("facts")
def facts(ctx: typer.Context, locale: Locale = "en") -> None:
    """List every fact a declaration can answer, with the provision it comes from."""
    t = translator(locale)
    compliance = compliance_for(settings_from(ctx))
    pack = compliance.ai_act_pack
    for stage in pack.stages:
        typer.echo(f"[{stage}]")
        for name, spec in pack.facts.items():
            if spec.stage == stage:
                typer.echo(f"  {name} ({spec.type.value}, {spec.ref})")
                typer.echo(f"      {t.text('fact.' + name)}")
    typer.echo("[attested by the organisation, read by the scanner]")
    for name, kind in compliance.scanner.declared_facts().items():
        typer.echo(f"  {name} ({kind.value})")
    typer.echo("")
    typer.echo("The questions are summaries, not the legal text. " + DISCLAIMER)


async def _classify(
    settings: Settings, tenant: str, key: str | None
) -> list[tuple[str, str, bool]]:
    compliance = compliance_for(settings)
    rows = []
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            systems = (
                [await compliance.inventory.get(session, tenant_id, key)]
                if key
                else await compliance.inventory.list(session, tenant_id)
            )
            for system in systems:
                current, created = await compliance.classifier.classify_system(session, system)
                rows.append((system.key, current.tier.value, created))
    return rows


@app.command("classify")
def classify(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="System key. Omit with --all.")] = None,
    everything: Annotated[
        bool, typer.Option("--all", help="Classify every declared system.")
    ] = False,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Classify a system, or all of them. An unchanged system keeps its classification."""
    if (key is None) != everything:
        raise fail(ArbiterError("name a system, or use --all"))
    for system, tier, created in run(_classify(settings_from(ctx), tenant, key)):
        typer.echo(f"{system:<32} {tier:<14} {'new' if created else 'unchanged'}")


async def _review(
    settings: Settings,
    tenant: str,
    key: str,
    decision: ReviewDecision,
    tier: RiskTier | None,
    reason: str,
    reviewer: str,
) -> EffectiveClassification:
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            system = await compliance.inventory.get(session, tenant_id, key)
            return await compliance.classifier.review(
                session,
                tenant_id,
                system.id,
                decision=decision,
                reviewer_id=await reviewer_for(session, tenant_id, reviewer),
                reason=reason,
                tier=tier,
            )


@app.command("review")
def review(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="System key.")],
    reviewer: Annotated[str, typer.Option("--reviewer", help="Name of the person who decides.")],
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm the indicative tier.")
    ] = False,
    override: Annotated[
        RiskTier | None, typer.Option("--override", help="Set another tier; needs --reason.")
    ] = None,
    reason: Annotated[str, typer.Option("--reason", help="Why.")] = "",
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Record a person's decision on the current classification of a system."""
    if confirm == (override is not None):
        raise fail(ArbiterError("use either --confirm or --override TIER"))
    decision = ReviewDecision.CONFIRMED if confirm else ReviewDecision.OVERRIDDEN
    current = run(_review(settings_from(ctx), tenant, key, decision, override, reason, reviewer))
    typer.echo(f"{key}: {current.tier.value}, {current.status} by {reviewer}")
