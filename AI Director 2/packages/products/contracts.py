"""Explicit Product Economics and direct-period COGS contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.finance.contracts import FinancialInputState
from packages.wb_core.contracts import TenantAccountScope


class ProductCostProfile(BaseModel):
    """A seller-provided unit cost with an effective period; never WB-derived."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    nm_id: str = Field(min_length=1, max_length=30)
    state: FinancialInputState
    unit_cogs: Decimal | None = None
    packaging_per_unit: Decimal | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)

    @field_validator("unit_cogs", "packaging_per_unit", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("product cost must not be float")
        return value

    @model_validator(mode="after")
    def require_explicit_cost_evidence(self) -> ProductCostProfile:
        values = (self.unit_cogs, self.packaging_per_unit)
        if self.state == FinancialInputState.PROVIDED:
            if all(value is None for value in values) or self.effective_from is None:
                raise ValueError("provided product cost requires a cost and effective_from")
        elif any(value is not None for value in values) or self.effective_from is not None or self.effective_to is not None:
            raise ValueError("unavailable product cost must not carry cost values or effective dates")
        if any(value is not None and value < 0 for value in values):
            raise ValueError("product costs must be positive or zero")
        if self.effective_from is not None and self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


class DirectPeriodCogsInput(BaseModel):
    """A signed external period COGS amount; no allocation is implied."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    operational_date: date
    state: FinancialInputState
    amount: Decimal | None = None
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    source_endpoint: str = Field(min_length=1, max_length=300)

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("period COGS amount must not be float")
        return value

    @model_validator(mode="after")
    def require_signed_amount_to_follow_state(self) -> DirectPeriodCogsInput:
        if self.state == FinancialInputState.PROVIDED:
            if self.amount is None or self.amount > 0:
                raise ValueError("provided period COGS requires a negative or zero Decimal")
        elif self.amount is not None:
            raise ValueError("unavailable period COGS must not carry an amount")
        return self
