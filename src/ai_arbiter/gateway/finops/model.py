"""FinOps tables: usage roll-ups and budgets."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import DecimalAmount, UTCDateTime


class UsageRollup(Base):
    """Usage of one scope on one day, in one currency.

    Kept up to date in the transaction that records each interaction, so that budgets
    read a handful of rows instead of scanning interactions.
    """

    __tablename__ = "usage_rollup"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    scope_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    # Every interaction recorded, whatever its outcome.
    requests: Mapped[int] = mapped_column(BigInteger, default=0)
    denied: Mapped[int] = mapped_column(BigInteger, default=0)
    failed: Mapped[int] = mapped_column(BigInteger, default=0)
    # Completed, but with no cost: no price for the model, or no token counts.
    unpriced: Mapped[int] = mapped_column(BigInteger, default=0)
    # Completed with token counts that were estimated, not reported by the provider.
    estimated: Mapped[int] = mapped_column(BigInteger, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_estimate: Mapped[Decimal] = mapped_column(DecimalAmount, default=Decimal(0))
    # The part of ``cost_estimate`` that comes from estimated token counts.
    estimated_cost: Mapped[Decimal] = mapped_column(DecimalAmount, default=Decimal(0))


class Budget(Base):
    __tablename__ = "budget"
    __table_args__ = (UniqueConstraint("tenant_id", "scope_type", "scope_id", "period"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[UUID] = mapped_column(Uuid)
    period: Mapped[str] = mapped_column(String(10))
    limit_amount: Mapped[Decimal] = mapped_column(DecimalAmount)
    currency: Mapped[str] = mapped_column(String(3))
    # Share of the limit, in percent, from which the budget counts as nearly used up.
    soft_threshold_percent: Mapped[int] = mapped_column(Integer, default=80)
    # A hard budget denies requests once the limit is reached; a soft one only warns.
    hard: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
