"""Immutable facts and results for the Stage 4 reconciliation slice."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.data.canonical import (
    CanonicalCurrency,
    CanonicalSalesFunnelProduct,
    CanonicalSourceMetadata,
)
from packages.wb_core.contracts import TenantAccountScope


class ReconciliationStatus(StrEnum):
    """Relationship and agreement state for one reconciled business identity."""

    MATCHED = "matched"
    UNMATCHED = "unmatched"
    PARTIAL = "partial"
    CONFLICT = "conflict"


class ReconciliationLagState(StrEnum):
    """Whether a future financial source is absent, present, or not applicable."""

    NOT_APPLICABLE = "not_applicable"
    AWAITING_FINANCIAL_CONFIRMATION = "awaiting_financial_confirmation"
    FINANCIAL_CONFIRMATION_PRESENT = "financial_confirmation_present"


class ReconciliationRule(StrEnum):
    """Explicit identity rules available to the initial source slice."""

    STRONG_SOURCE_RECORD_ID = "strong_source_record_id"
    COMPOSITE_OPERATIONAL_DATE_AND_PRODUCT = "composite_operational_date_and_product"


class ReconciliationDiagnosticCode(StrEnum):
    """Machine-readable explanation codes; no finance conclusions are implied."""

    STRONG_IDENTITY_MATCH = "strong_identity_match"
    COMPOSITE_IDENTITY_MATCH = "composite_identity_match"
    SINGLE_SOURCE_FACT = "single_source_fact"
    QUANTITY_CONFLICT = "quantity_conflict"
    AMOUNT_CONFLICT = "amount_conflict"
    CURRENCY_CONFLICT = "currency_conflict"
    MISSING_QUANTITY = "missing_quantity"
    MISSING_AMOUNT = "missing_amount"
    FINANCIAL_CONFIRMATION_PENDING = "financial_confirmation_pending"
    COHORT_METRIC_RETAINED = "cohort_metric_retained"


class ReconciliationDiagnostic(BaseModel):
    """Immutable, structured evidence for a reconciliation decision."""

    model_config = ConfigDict(frozen=True)

    code: ReconciliationDiagnosticCode
    rule: ReconciliationRule | None = None
    field_name: str | None = Field(default=None, min_length=1, max_length=100)
    source_object_ids: tuple[str, ...] = ()


class ReconciliationIdentity(BaseModel):
    """Identity selected by an explicit rule, without editing any source fact."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    rule: ReconciliationRule
    value: str = Field(min_length=1, max_length=500)
    operational_date: date
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)


class CanonicalSalesConfirmationFact(BaseModel):
    """Synthetic operational confirmation, deliberately separate from finance facts."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    source_event_id: str | None = Field(default=None, min_length=1, max_length=300)
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    quantity: int | None = None
    source_amount: Decimal | None = None
    currency: CanonicalCurrency | None = None


class CanonicalCohortMetricFact(BaseModel):
    """Synthetic canonical cohort metric; never an order, sale, or finance fact."""

    model_config = ConfigDict(frozen=True)

    source_metadata: CanonicalSourceMetadata
    operational_date: date
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)
    seller_sku: str | None = Field(default=None, min_length=1, max_length=150)
    buyout_count: int | None = None
    buyout_sum: Decimal | None = None
    currency: CanonicalCurrency | None = None
    metric_kind: str = Field(default="buyout_cohort", frozen=True)

    @model_validator(mode="after")
    def require_cohort_metric_kind(self) -> CanonicalCohortMetricFact:
        if self.metric_kind != "buyout_cohort":
            raise ValueError("metric_kind must remain buyout_cohort")
        return self


class ReconciliationResult(BaseModel):
    """Immutable relation among source facts; it never contains corrected values."""

    model_config = ConfigDict(frozen=True)

    reconciliation_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity: ReconciliationIdentity
    sales_funnel_facts: tuple[CanonicalSalesFunnelProduct, ...] = ()
    confirmation_facts: tuple[CanonicalSalesConfirmationFact, ...] = ()
    cohort_metric_facts: tuple[CanonicalCohortMetricFact, ...] = ()
    status: ReconciliationStatus
    diagnostics: tuple[ReconciliationDiagnostic, ...]
    operational_dates: tuple[date, ...]
    financial_dates: tuple[date, ...] = ()
    lag_state: ReconciliationLagState

    @field_validator("financial_dates")
    @classmethod
    def require_unique_financial_dates(cls, values: tuple[date, ...]) -> tuple[date, ...]:
        if tuple(sorted(set(values))) != values:
            raise ValueError("financial_dates must be unique and sorted")
        return values

    @model_validator(mode="after")
    def require_consistent_result_state(self) -> ReconciliationResult:
        if not self.sales_funnel_facts and not self.confirmation_facts:
            raise ValueError("at least one operational source fact is required")
        if tuple(sorted(set(self.operational_dates))) != self.operational_dates:
            raise ValueError("operational_dates must be unique and sorted")
        if self.identity.operational_date not in self.operational_dates:
            raise ValueError("identity operational_date must belong to operational_dates")
        if self.lag_state == ReconciliationLagState.AWAITING_FINANCIAL_CONFIRMATION and self.financial_dates:
            raise ValueError("awaiting financial confirmation cannot include financial dates")
        if self.lag_state == ReconciliationLagState.FINANCIAL_CONFIRMATION_PRESENT and not self.financial_dates:
            raise ValueError("financial confirmation present requires financial dates")
        return self

    @property
    def retrieved_at_values(self) -> tuple[datetime, ...]:
        """Expose source retrieval provenance without assigning it event semantics."""

        values = [fact.source_metadata.retrieved_at for fact in self.sales_funnel_facts]
        values.extend(fact.source_metadata.retrieved_at for fact in self.confirmation_facts)
        values.extend(fact.source_metadata.retrieved_at for fact in self.cohort_metric_facts)
        return tuple(sorted(set(values)))

    @field_validator("sales_funnel_facts", "confirmation_facts", "cohort_metric_facts")
    @classmethod
    def require_utc_provenance(cls, facts: tuple[object, ...]) -> tuple[object, ...]:
        for fact in facts:
            source_metadata = getattr(fact, "source_metadata")
            retrieved_at = source_metadata.retrieved_at
            if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != timezone.utc.utcoffset(retrieved_at):
                raise ValueError("source retrieved_at must be timezone-aware UTC")
        return facts
