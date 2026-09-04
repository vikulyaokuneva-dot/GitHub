"""Tax facts that distinguish sourced, missing, and unresolved states."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.finance.contracts import FinancialInputState
from packages.wb_core.contracts import TenantAccountScope


class TaxRateBasis(StrEnum):
    """The declared base a seller rate may be applied to; there is no implicit base."""

    REALIZED_REVENUE = "realized_revenue"


class TaxRateSetting(BaseModel):
    """A seller-provided tax rate in percent.

    This is a *source declaration*, not a tax amount: the amount is derived by
    :func:`packages.tax.service.tax_input_from_rate` and then enters the Finance
    Kernel as an ordinary :class:`SourcedTaxInput`.  The kernel itself still
    refuses to invent any tax, and a missing rate stays missing rather than 0.
    """

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    rate_percent: Decimal
    basis: TaxRateBasis = TaxRateBasis.REALIZED_REVENUE
    source: str = Field(default="seller_financial_setting", min_length=1, max_length=100)
    updated_at: datetime

    @field_validator("rate_percent", mode="before")
    @classmethod
    def reject_float_rate(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("tax rate must not be float")
        return value

    @model_validator(mode="after")
    def require_rate_within_percent_range(self) -> TaxRateSetting:
        if self.rate_percent < 0:
            raise ValueError("tax rate must be positive or zero")
        if self.rate_percent > Decimal("100"):
            raise ValueError("tax rate must not exceed 100 percent")
        return self


class SourcedTaxInput(BaseModel):
    """One tax source value; no rate, revenue base, or fallback formula is accepted."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    operational_date: date
    financial_date: date | None = None
    state: FinancialInputState
    amount: Decimal | None = None
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    source_endpoint: str = Field(min_length=1, max_length=300)
    diagnostic: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("tax amount must not be float")
        return value

    @model_validator(mode="after")
    def require_sourced_signed_tax_or_explicit_absence(self) -> SourcedTaxInput:
        if self.state == FinancialInputState.PROVIDED:
            if self.amount is None or self.amount > 0:
                raise ValueError("provided tax requires a negative or zero sourced Decimal")
        elif self.amount is not None:
            raise ValueError("missing or unresolved tax must not carry an amount")
        if self.state != FinancialInputState.PROVIDED and self.diagnostic is None:
            raise ValueError("missing or unresolved tax requires a diagnostic")
        return self
