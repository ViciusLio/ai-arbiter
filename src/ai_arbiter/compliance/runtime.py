"""The services of the compliance toolkit, built once from the settings."""

from dataclasses import dataclass

from ai_arbiter.compliance.classifier.service import ClassifierService, InventorySystemDirectory
from ai_arbiter.compliance.findings.service import FindingService
from ai_arbiter.compliance.inventory.service import InventoryService
from ai_arbiter.compliance.scanner.service import ScannerService
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.ports import AuditLog, EventBus, TargetDirectory
from ai_arbiter.core.rules import RulePack, load_packaged_pack, load_rule_pack

AI_ACT_PACK = "ai-act"
SCAN_PACK = "scan"


@dataclass
class ComplianceRuntime:
    settings: Settings
    clock: Clock
    audit: AuditLog
    bus: EventBus
    ai_act_pack: RulePack
    scan_pack: RulePack
    inventory: InventoryService
    classifier: ClassifierService
    findings: FindingService
    scanner: ScannerService
    directory: InventorySystemDirectory


def build_compliance(
    settings: Settings,
    *,
    audit: AuditLog,
    bus: EventBus,
    clock: Clock | None = None,
    targets: TargetDirectory | None = None,
) -> ComplianceRuntime:
    """Load the rule packs and wire the services. Raises ``RulePackError``."""
    clock = clock if clock is not None else SystemClock()
    compliance = settings.compliance
    ai_act = (
        load_rule_pack(compliance.ai_act_pack)
        if compliance.ai_act_pack is not None
        else load_packaged_pack(AI_ACT_PACK)
    )
    scan = (
        load_rule_pack(compliance.scan_pack)
        if compliance.scan_pack is not None
        else load_packaged_pack(SCAN_PACK)
    )
    classifier = ClassifierService(ai_act, audit, bus, clock)
    findings = FindingService(audit, clock)
    scanner = ScannerService(scan, classifier, findings, audit, clock, targets)
    known_facts = {name: spec.type for name, spec in ai_act.facts.items()}
    known_facts.update(scanner.declared_facts())
    return ComplianceRuntime(
        settings=settings,
        clock=clock,
        audit=audit,
        bus=bus,
        ai_act_pack=ai_act,
        scan_pack=scan,
        inventory=InventoryService(audit, bus, known_facts, clock),
        classifier=classifier,
        findings=findings,
        scanner=scanner,
        directory=InventorySystemDirectory(classifier),
    )
