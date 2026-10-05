"""A system that names several projects, and a key that belongs to a system through its
project (ADR-0059)."""

from typing import Any
from uuid import UUID

from ai_arbiter.compliance.inventory.declarations import SystemDeclaration
from ai_arbiter.compliance.inventory.discovery import discover
from ai_arbiter.compliance.runtime import ComplianceRuntime
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.persistence.database import Database
from tests.integration.test_compliance import declare, scan
from tests.integration.test_discovery import SINCE, compliance, declarations, traffic

__all__ = ["compliance", "declarations"]

BANK, RETAIL, LAB = new_id(), new_id(), new_id()


def naming(
    declarations: dict[str, SystemDeclaration], key: str, **projects: Any
) -> dict[str, SystemDeclaration]:
    return {key: declarations[key].model_copy(update=projects)}


async def changes(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declaration: SystemDeclaration,
) -> tuple[str, tuple[UUID, ...]]:
    async with database.transaction() as session:
        declared = await compliance.inventory.declare(session, tenant_id, declaration)
        return declared.change, await compliance.inventory.projects(session, declared.system)


async def test_a_declaration_names_several_projects_and_a_change_of_them_is_a_change(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    system = declarations["invoice-data-extraction"]
    both = system.model_copy(update={"project_ids": [BANK, RETAIL, BANK]})
    one = system.model_copy(update={"project_ids": [RETAIL]})
    earlier_form = system.model_copy(update={"project_id": RETAIL})

    first = await changes(compliance, database, tenant_id, both)
    again = await changes(compliance, database, tenant_id, both)
    fewer = await changes(compliance, database, tenant_id, one)
    same = await changes(compliance, database, tenant_id, earlier_form)
    none = await changes(compliance, database, tenant_id, system)

    assert first == ("created", tuple(sorted((BANK, RETAIL), key=str)))
    assert again[0] == "unchanged"
    assert fewer == ("changed", (RETAIL,))
    # A file written before several projects could be named still means what it meant.
    assert same == ("unchanged", (RETAIL,))
    assert none == ("changed", ())


async def test_the_requests_of_every_named_project_count_for_the_system_and_are_no_candidate(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    named = naming(declarations, "invoice-data-extraction", project_ids=[BANK, RETAIL])
    await declare(compliance, database, tenant_id, named)
    await traffic(database, tenant_id, count=3, project_id=BANK)
    await traffic(database, tenant_id, count=2, project_id=RETAIL)
    await traffic(database, tenant_id, count=4, project_id=LAB)

    await scan(compliance, database, tenant_id)

    async with database.session() as session:
        candidates = await discover(session, tenant_id, SINCE)
        system = await compliance.inventory.get(session, tenant_id, "invoice-data-extraction")
        _, observed = await compliance.scanner.observe(session, system)
    assert [item.reference for item in candidates] == [f"project:{LAB}"]
    assert observed["requests"] == 5
