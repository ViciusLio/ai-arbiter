"""Every scenario shipped with the package produces the outcomes it states (ADR-0043)."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from ai_arbiter.compliance.findings.model import Finding
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.compliance.simulation.model import (
    ScenarioError,
    load_scenario,
    packaged_scenarios,
    parse_scenario,
)
from ai_arbiter.compliance.simulation.runner import SIMULATION_SOURCE, run_scenario
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.errors import NotFoundError
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from tests.integration.test_compliance import FixedClock

REVIEWER = new_id()
SCENARIOS = packaged_scenarios()


@pytest.fixture
def compliance() -> ComplianceRuntime:
    clock = FixedClock()
    return build_compliance(
        load_settings(), audit=DatabaseAuditLog(clock), bus=InProcessEventBus(), clock=clock
    )


def test_three_scenarios_are_shipped_and_each_is_described_in_both_languages() -> None:
    assert SCENARIOS == ["first-inventory", "inventory-in-order", "shadow-ai"]
    for name in SCENARIOS:
        scenario = load_scenario(name)
        assert scenario.title.text("en") != scenario.title.text("it")
        assert scenario.description.text("en") != scenario.description.text("it")
    with pytest.raises(NotFoundError, match="available: first-inventory"):
        load_scenario("no-such-scenario")


def test_no_two_scenarios_declare_the_same_system_or_the_same_group() -> None:
    # They are loaded into one tenant: a shared key would let one rewrite the other.
    keys = [d.key for name in SCENARIOS for d in load_scenario(name).declarations()]
    groups = [
        group
        for name in SCENARIOS
        for group in {item.group for item in load_scenario(name).traffic if item.group}
    ]

    assert len(keys) == len(set(keys)) == 8
    assert len(groups) == len(set(groups))


@pytest.mark.parametrize("name", SCENARIOS)
async def test_a_scenario_produces_the_tiers_findings_and_candidates_it_expects(
    name: str, compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    scenario = load_scenario(name)

    async with database.transaction() as session:
        result = await run_scenario(session, tenant_id, compliance, scenario, reviewer_id=REVIEWER)

    for system in result.systems:
        assert (system.key, system.tier) == (system.key, system.expected_tier)
        assert (system.key, system.findings) == (system.key, system.expected_findings)
    assert result.candidates == result.expected_candidates
    assert result.as_expected
    async with database.session() as session:
        # Nothing about the tenant as a whole beyond the candidates the scenario names.
        tenant_wide = (
            await session.scalars(
                select(Finding.rule_id).where(
                    Finding.tenant_id == tenant_id, Finding.ai_system_id.is_(None)
                )
            )
        ).all()
        report = await compliance.audit.verify(session, tenant_id)
    assert tenant_wide == ["SCAN-UNDECLARED-SYSTEM-CANDIDATE"] * len(result.candidates)
    assert report.ok


async def test_running_a_scenario_again_adds_nothing(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    scenario = load_scenario("shadow-ai")

    async def count() -> tuple[int, int]:
        async with database.session() as session:
            requests = await session.scalar(
                select(func.count()).where(Interaction.source == SIMULATION_SOURCE)
            )
            findings = await session.scalar(select(func.count()).select_from(Finding))
        return int(requests or 0), int(findings or 0)

    async with database.transaction() as session:
        await run_scenario(session, tenant_id, compliance, scenario, reviewer_id=REVIEWER)
    first = await count()
    async with database.transaction() as session:
        again = await run_scenario(session, tenant_id, compliance, scenario, reviewer_id=REVIEWER)

    assert first == (205, 5)
    assert await count() == first
    assert again.as_expected


async def test_scenarios_live_together_in_one_tenant_and_stay_out_of_another(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    async with database.transaction() as session:
        results = [
            await run_scenario(
                session, tenant_id, compliance, load_scenario(name), reviewer_id=REVIEWER
            )
            for name in SCENARIOS
        ]
        # Run again after the others were loaded: each still finds what it expects.
        again = [
            await run_scenario(
                session, tenant_id, compliance, load_scenario(name), reviewer_id=REVIEWER
            )
            for name in SCENARIOS
        ]

    assert all(result.as_expected for result in results)
    assert all(result.as_expected for result in again)
    async with database.session() as session:
        assert await compliance.inventory.list(session, other_tenant_id) == []
        elsewhere = await session.scalar(
            select(func.count()).where(Interaction.tenant_id == other_tenant_id)
        )
    assert elsewhere == 0


BASE = """
scenario: tiny
title: {en: A, it: B}
description: {en: A, it: B}
inventory:
  systems:
    - {key: one, name: One}
expected:
  systems:
    one: {tier: undetermined}
"""


@pytest.mark.parametrize(
    ("addition", "problem"),
    [
        ("owned: [two]", "owned: 'two' is not a system of the scenario"),
        ("reviews: [{system: two}]", "reviews: 'two' is not a system"),
        ("traffic: [{system: two, requests: 1, model: m}]", "traffic: 'two' is not a system"),
        ("traffic: [{requests: 1, model: m}]", "name either the system or the group"),
        ("traffic: [{group: g, system: one, requests: 1, model: m}]", "name either the system"),
        ("traffic: [{group: g, requests: 1, model: m, prompt: hello}]", "traffic.0.prompt"),
        ("code: print(1)", "code: Extra inputs are not permitted"),
    ],
)
def test_a_scenario_that_contradicts_itself_is_refused(addition: str, problem: str) -> None:
    assert parse_scenario(BASE, origin="tiny").scenario == "tiny"

    with pytest.raises(ScenarioError, match=problem):
        parse_scenario(BASE + addition + "\n", origin="tiny")


def test_a_scenario_must_say_what_it_expects_of_every_system() -> None:
    text = BASE.replace("one: {tier: undetermined}", "other: {tier: minimal}")

    with pytest.raises(ScenarioError, match="must name every system"):
        parse_scenario(text, origin="tiny")
    with pytest.raises(ScenarioError, match="not valid YAML"):
        parse_scenario("scenario: [", origin="tiny")
