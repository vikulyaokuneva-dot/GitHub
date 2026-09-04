"""User-provided financial parameters that feed the existing finance pipeline.

This package owns *declarations* only: what the seller says about unit cost,
tax rate, and period finality.  It calculates nothing.  Every value it exposes
is handed to the existing domain contracts (``ProductCostProfile``,
``TaxRateSetting``, ``FinancialFinalityInput``) and the Finance Kernel stays
the single owner of the financial result.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from packages.finance.contracts import FinancialFinality, FinancialFinalityInput
from packages.products.contracts import ProductCostProfile
from packages.tax.contracts import TaxRateSetting
from packages.wb_core.contracts import TenantAccountScope


class PeriodFinalityConfirmation(BaseModel):
    """An explicit seller statement that one operational day is financially final.

    WB finance detail carries no finality signal, so the kernel keeps a period
    PARTIAL and refuses to publish ``net_profit``.  This confirmation is the
    seller's own evidence: it is passed through the *existing* ``finality``
    input of the audit boundary, and its ``source`` makes clear that the claim
    comes from the seller rather than from Wildberries.
    """

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    operational_date: date
    confirmed_at: datetime
    evidence_code: str = Field(default="seller_confirmed_period", min_length=1, max_length=100)

    def to_financial_finality_input(self) -> FinancialFinalityInput:
        return FinancialFinalityInput(
            source="seller_confirmation",
            source_record_id=f"finality:{self.scope.account_id}:{self.operational_date.isoformat()}",
            operational_date=self.operational_date,
            financial_date=self.operational_date,
            finality=FinancialFinality.FINAL,
            evidence_code=self.evidence_code,
        )


class FinancialSettings(BaseModel):
    """The user-provided inputs one audit run may legitimately claim."""

    model_config = ConfigDict(frozen=True)

    product_costs: tuple[ProductCostProfile, ...] = ()
    tax_rate: TaxRateSetting | None = None
    finality_confirmation: PeriodFinalityConfirmation | None = None

    @classmethod
    def empty(cls) -> "FinancialSettings":
        return cls()

    def applicable_product_costs(self, operational_date: date) -> tuple[ProductCostProfile, ...]:
        """Profiles whose declared effective window covers the audited day."""

        return tuple(
            profile
            for profile in self.product_costs
            if profile.effective_from is not None
            and profile.effective_from <= operational_date
            and (profile.effective_to is None or profile.effective_to >= operational_date)
        )
