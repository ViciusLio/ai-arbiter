"""``arbiter demo``: load a simulation scenario and show what the toolkit makes of it."""

from typing import Annotated

import typer

from ai_arbiter.cli.common import (
    compliance_for,
    fail,
    open_database,
    reviewer_for,
    run,
    settings_from,
)
from ai_arbiter.cli.systems import Locale, translator
from ai_arbiter.compliance.simulation.model import load_scenario, packaged_scenarios
from ai_arbiter.compliance.simulation.runner import ScenarioResult, run_scenario
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.i18n import Translator
from ai_arbiter.core.persistence.tenant import ensure_tenant

app = typer.Typer(help="Simulation scenarios: invented systems and traffic.", no_args_is_help=True)

# Scenarios are loaded here and nowhere else, so that invented data never mixes with
# an organisation's own.
DEMO_TENANT = "demo"
DEMO_REVIEWER = "Demo reviewer"


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
