"""AI Act vocabulary shared by the gateway and the compliance toolkit."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActorRole(StrEnum):
    """Operator roles of the AI Act (ADR-0007). One organisation can hold several."""

    PROVIDER = "provider"
    DEPLOYER = "deployer"
    IMPORTER = "importer"
    DISTRIBUTOR = "distributor"
    AUTHORISED_REPRESENTATIVE = "authorised_representative"
    PRODUCT_MANUFACTURER = "product_manufacturer"


class RiskTier(StrEnum):
    OUT_OF_SCOPE = "out_of_scope"
    PROHIBITED = "prohibited"
    HIGH_RISK = "high_risk"
    TRANSPARENCY = "transparency"
    MINIMAL = "minimal"
    # Not classified, or classified with facts missing that could change the outcome.
    UNDETERMINED = "undetermined"


# From the most to the least severe. ``undetermined`` is not on this scale.
TIER_SEVERITY = (
    RiskTier.PROHIBITED,
    RiskTier.HIGH_RISK,
    RiskTier.TRANSPARENCY,
    RiskTier.MINIMAL,
)


class SystemRiskProfile(BaseModel):
    """What the gateway needs to know about the system behind a request."""

    model_config = ConfigDict(frozen=True)

    ai_system_id: UUID | None
    tier: RiskTier = RiskTier.UNDETERMINED
    # False while the classification awaits review by a person (ADR-0037).
    reviewed: bool = False
    classification_id: UUID | None = None
