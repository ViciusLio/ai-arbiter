"""Classify declared systems, keep the history, and record what a person decided."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.classifier.engine import (
    ClassificationResult,
    classify,
    ordered_questions,
)
from ai_arbiter.compliance.classifier.model import (
    Classification,
    ClassificationReview,
    ReviewDecision,
    SystemClassified,
)
from ai_arbiter.compliance.inventory.model import AISystem, AISystemRole
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.domain.risk import ActorRole, RiskTier, SystemRiskProfile
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.core.ports import AuditLog, EventBus
from ai_arbiter.core.rules import RulePack

MIN_REASON_LENGTH = 10


@dataclass(frozen=True)
class EffectiveClassification:
    """A classification with what a person decided about it, if anyone has."""

    classification: Classification
    review: ClassificationReview | None

    @property
    def tier(self) -> RiskTier:
        return RiskTier(self.review.tier if self.review else self.classification.tier)

    @property
    def reviewed(self) -> bool:
        return self.review is not None

    @property
    def status(self) -> str:
        return self.review.decision if self.review else "proposed"


class ClassifierService:
    def __init__(
        self, pack: RulePack, audit: AuditLog, bus: EventBus, clock: Clock | None = None
    ) -> None:
        self.pack = pack
        self._audit = audit
        self._bus = bus
        self._clock = clock if clock is not None else SystemClock()

    async def _roles(self, session: AsyncSession, system: AISystem) -> frozenset[ActorRole]:
        roles = await session.scalars(
            select(AISystemRole.role).where(AISystemRole.ai_system_id == system.id)
        )
        return frozenset(ActorRole(role) for role in roles)

    async def evaluate(self, session: AsyncSession, system: AISystem) -> ClassificationResult:
        """Classify without storing anything."""
        return classify(self.pack, system.attributes or {}, await self._roles(session, system))

    def questions(self, result: ClassificationResult) -> list[str]:
        """The facts still to be answered, in questionnaire order."""
        return ordered_questions(self.pack, result.missing_facts)

    async def current(
        self, session: AsyncSession, tenant_id: UUID, system_id: UUID
    ) -> EffectiveClassification | None:
        classification = await session.scalar(
            select(Classification).where(
                Classification.tenant_id == tenant_id,
                Classification.ai_system_id == system_id,
                Classification.superseded_by.is_(None),
            )
        )
        if classification is None:
            return None
        return EffectiveClassification(classification, await self._review(session, classification))

    async def _review(
        self, session: AsyncSession, classification: Classification
    ) -> ClassificationReview | None:
        return await session.scalar(
            select(ClassificationReview)
            .where(ClassificationReview.classification_id == classification.id)
            .order_by(ClassificationReview.created_at.desc(), ClassificationReview.id.desc())
            .limit(1)
        )

    async def history(
        self, session: AsyncSession, tenant_id: UUID, system_id: UUID
    ) -> Sequence[Classification]:
        return (
            await session.scalars(
                select(Classification)
                .where(
                    Classification.tenant_id == tenant_id, Classification.ai_system_id == system_id
                )
                .order_by(Classification.created_at, Classification.id)
            )
        ).all()

    async def classify_system(
        self, session: AsyncSession, system: AISystem, *, actor_id: UUID | None = None
    ) -> tuple[EffectiveClassification, bool]:
        """Classify and store. Returns the classification and whether it is new.

        Nothing is written when facts, roles and pack are the same as last time: the
        existing classification, with its review, stays in force.
        """
        result = await self.evaluate(session, system)
        existing = await self.current(session, system.tenant_id, system.id)
        if (
            existing is not None
            and existing.classification.input_digest == result.decision.input_digest
        ):
            return existing, False

        classification = Classification(
            tenant_id=system.tenant_id,
            ai_system_id=system.id,
            rulepack=self.pack.pack,
            rulepack_version=self.pack.version,
            regulation_as_of=self.pack.regulation.as_of if self.pack.regulation else None,
            tier=result.tier.value,
            obligations=[obligation.as_json() for obligation in result.obligations],
            trace=list(result.decision.audit_payload()["matches"]),  # type: ignore[arg-type]
            missing_facts=self.questions(result),
            input_digest=result.decision.input_digest,
            created_at=self._clock.now(),
        )
        session.add(classification)
        await session.flush()
        if existing is not None:
            existing.classification.superseded_by = classification.id
        await self._audit.append(
            session,
            system.tenant_id,
            AuditRecord.of_decision(
                result.decision,
                action="system.classified",
                actor_id=actor_id,
                resource_type="ai_system",
                resource_id=str(system.id),
            ),
        )
        await self._bus.publish(
            SystemClassified(
                tenant_id=system.tenant_id,
                ai_system_id=system.id,
                classification_id=classification.id,
            ),
            session=session,
        )
        await session.flush()
        return EffectiveClassification(classification, None), True

    async def review(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        system_id: UUID,
        *,
        decision: ReviewDecision,
        reviewer_id: UUID,
        reason: str = "",
        tier: RiskTier | None = None,
    ) -> EffectiveClassification:
        """Record a person's decision on the current classification (ADR-0037).

        Confirming keeps the engine's tier. Overriding sets another one and needs a
        reason. A classification that is ``undetermined`` cannot be confirmed: either the
        missing facts are answered, or the reviewer overrides with a reason.
        """
        current = await self.current(session, tenant_id, system_id)
        if current is None:
            raise NotFoundError("the system has no classification to review")
        classification = current.classification
        if decision is ReviewDecision.CONFIRMED:
            if tier is not None and tier.value != classification.tier:
                raise ConflictError("to set a different tier, override instead of confirming")
            if classification.tier == RiskTier.UNDETERMINED.value:
                raise ConflictError(
                    "an undetermined classification cannot be confirmed: answer the missing "
                    "facts, or override it with a reason"
                )
            effective = RiskTier(classification.tier)
        else:
            if tier is None or tier is RiskTier.UNDETERMINED:
                raise ConflictError("an override needs the tier that should hold")
            if len(reason.strip()) < MIN_REASON_LENGTH:
                raise ConflictError(
                    f"an override needs a reason of at least {MIN_REASON_LENGTH} characters"
                )
            effective = tier
        review = ClassificationReview(
            tenant_id=tenant_id,
            classification_id=classification.id,
            decision=decision.value,
            tier=effective.value,
            reviewer_id=reviewer_id,
            reason=reason.strip(),
            created_at=self._clock.now(),
        )
        session.add(review)
        await session.flush()
        await self._audit.append(
            session,
            tenant_id,
            AuditRecord(
                action=f"classification.{decision.value}",
                outcome=f"tier:{effective.value}",
                actor_id=reviewer_id,
                resource_type="classification",
                resource_id=str(classification.id),
            ),
        )
        return EffectiveClassification(classification, review)


class InventorySystemDirectory:
    """Implements the ``SystemDirectory`` port from the current classifications."""

    def __init__(self, classifier: ClassifierService) -> None:
        self._classifier = classifier

    async def resolve(
        self, session: AsyncSession, tenant_id: UUID, ai_system_id: UUID | None
    ) -> SystemRiskProfile:
        if ai_system_id is None:
            return SystemRiskProfile(ai_system_id=None)
        current = await self._classifier.current(session, tenant_id, ai_system_id)
        if current is None:
            return SystemRiskProfile(ai_system_id=ai_system_id)
        return SystemRiskProfile(
            ai_system_id=ai_system_id,
            tier=current.tier,
            reviewed=current.reviewed,
            classification_id=current.classification.id,
        )
