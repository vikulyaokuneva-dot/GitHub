"""Contract-only inputs and outputs for a future pure Finance Kernel."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.data.canonical import CanonicalCurrency
from packages.reconciliation.contracts import ReconciliationResult
from packages.wb_core.contracts import TenantAccountScope


class FinancialComponent(StrEnum):
    """Named financial components with a single target owner each."""

    REALIZED_REVENUE = "realized_revenue"
    RETURN_REVENUE_ADJUSTMENT = "return_revenue_adjustment"
    MARKETPLACE_COMMISSION = "marketplace_commission"
    LOGISTICS = "logistics"
    REVERSE_LOGISTICS = "reverse_logistics"
    ACQUIRING = "acquiring"
    ACCEPTANCE = "acceptance"
    STORAGE = "storage"
    PENALTIES = "penalties"
    OTHER_MARKETPLACE_DEDUCTIONS = "other_marketplace_deductions"
    ADVERTISING = "advertising"
    TAX = "tax"
    COGS = "cogs"
    PACKAGING = "packaging"
    REBILL_LOGISTICS = "rebill_logistics"


class FinancialInputState(StrEnum):
    """Availability of a component is independent from its monetary value."""

    PROVIDED = "provided"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"


class FinancialComponentStatus(StrEnum):
    """How a result component can safely be interpreted by a consumer."""

    AVAILABLE = "available"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


class FinancialStatus(StrEnum):
    """Overall status for a period P&L result, never a monetary amount."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    AWAITING_FINANCIAL_CONFIRMATION = "awaiting_financial_confirmation"
    CONFLICT = "conflict"
    INSUFFICIENT_DATA = "insufficient_data"


class RevenueBasis(StrEnum):
    """Named financial views; no generic field may hide their different meanings."""

    REALIZED_GROSS = "realized_gross"
    BUYER_DISCOUNTED = "buyer_discounted"
    SELLER_PAYOUT = "seller_payout"


class AdvertisingAttribution(StrEnum):
    """Granularity that is evidenced by the advertising source."""

    DIRECT = "direct"
    PERIOD_LEVEL = "period_level"
    UNKNOWN = "unknown"


class FinancialFinality(StrEnum):
    """Evidence-based financial finality, separate from row presence and lag."""

    PROVISIONAL = "provisional"
    FINAL = "final"
    UNKNOWN = "unknown"


class RebillLogisticsClassification(StrEnum):
    """One rebill must be classified once before Finance Kernel aggregation."""

    LOGISTICS = "logistics"
    REVERSE_LOGISTICS = "reverse_logistics"


class UnresolvedCogsEvent(StrEnum):
    """Events whose COGS effect must not be inferred by the core kernel."""

    RETURN = "return"
    CANCELLATION = "cancellation"
    PARTIAL_RETURN = "partial_return"


class MoneyRoundingPolicy(StrEnum):
    """The sole Stage 5 rounding policy; calculation implementation comes later."""

    AGGREGATE_THEN_HALF_UP_TO_CENT = "aggregate_then_half_up_to_cent"


class FinancialComponentInput(BaseModel):
    """One signed Decimal input with component-level source provenance."""

    model_config = ConfigDict(frozen=True)

    component: FinancialComponent
    state: FinancialInputState
    amount: Decimal | None = None
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    source_endpoint: str = Field(min_length=1, max_length=300)
    operational_date: date
    financial_date: date | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("financial amount must not be float")
        return value

    @model_validator(mode="after")
    def require_amount_to_follow_state(self) -> FinancialComponentInput:
        amount_states = {FinancialInputState.PROVIDED, FinancialInputState.UNRESOLVED}
        if self.state in amount_states and self.amount is None:
            raise ValueError("provided or unresolved financial component requires a Decimal amount")
        if self.state not in amount_states and self.amount is not None:
            raise ValueError("missing or not_applicable component must not carry an amount")
        if self.state != FinancialInputState.PROVIDED:
            return self
        if self.amount is not None and self.component == FinancialComponent.REALIZED_REVENUE and self.amount < 0:
            raise ValueError("realized_revenue must be positive or zero")
        if self.amount is not None and self.component != FinancialComponent.REALIZED_REVENUE and self.amount > 0:
            raise ValueError("deduction and return components must be negative or zero")
        return self


class RevenueBasisInput(BaseModel):
    """Explicit revenue view from a source row; amount semantics cannot be overloaded."""

    model_config = ConfigDict(frozen=True)

    basis: RevenueBasis
    amount: Decimal
    quantity: int = Field(gt=0)
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    source_field: str = Field(min_length=1, max_length=100)
    operational_date: date
    financial_date: date | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("revenue basis amount must not be float")
        return value

    @model_validator(mode="after")
    def require_non_negative_amount(self) -> RevenueBasisInput:
        if self.amount < 0:
            raise ValueError("revenue basis amount must be positive or zero")
        return self


class AdvertisingExpenseInput(BaseModel):
    """Advertising expense with declared attribution granularity and date scope."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal
    attribution: AdvertisingAttribution
    period_start: date
    period_end: date
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    campaign_id: str | None = Field(default=None, min_length=1, max_length=100)
    nm_id: str | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("advertising amount must not be float")
        return value

    @model_validator(mode="after")
    def require_attribution_shape(self) -> AdvertisingExpenseInput:
        if self.amount > 0:
            raise ValueError("advertising expense must be negative or zero")
        if self.period_end < self.period_start:
            raise ValueError("advertising period_end must not precede period_start")
        if self.attribution == AdvertisingAttribution.DIRECT and self.nm_id is None:
            raise ValueError("direct advertising attribution requires nm_id")
        if self.attribution != AdvertisingAttribution.DIRECT and self.nm_id is not None:
            raise ValueError("period-level or unknown advertising must not claim nm_id attribution")
        return self


class FinancialFinalityInput(BaseModel):
    """Finality evidence for one financial record; a record alone is provisional."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    operational_date: date
    financial_date: date | None = None
    finality: FinancialFinality
    evidence_code: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_finality_evidence(self) -> FinancialFinalityInput:
        if self.finality == FinancialFinality.FINAL and self.financial_date is None:
            raise ValueError("final financial record requires financial_date")
        return self


class RebillLogisticsInput(BaseModel):
    """A rebill source value retained for unresolved Stage 6 diagnostics."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal
    classification: RebillLogisticsClassification
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    operational_date: date
    financial_date: date | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("rebill logistics amount must not be float")
        return value

    @model_validator(mode="after")
    def require_negative_expense_amount(self) -> RebillLogisticsInput:
        if self.amount > 0:
            raise ValueError("rebill logistics expense must be negative or zero")
        return self


class CogsAllocationInput(BaseModel):
    """Explicit unit cost and caller-authoritative realized quantity."""

    model_config = ConfigDict(frozen=True)

    nm_id: str = Field(min_length=1, max_length=30)
    quantity: int = Field(gt=0)
    state: FinancialInputState
    unit_cogs: Decimal | None = None
    packaging_per_unit: Decimal | None = None
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    effective_date: date

    @field_validator("unit_cogs", "packaging_per_unit", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("COGS allocation values must not be float")
        return value

    @model_validator(mode="after")
    def require_available_costs_to_follow_state(self) -> CogsAllocationInput:
        costs = (self.unit_cogs, self.packaging_per_unit)
        if self.state == FinancialInputState.PROVIDED and all(value is None for value in costs):
            raise ValueError("provided COGS allocation requires unit_cogs or packaging_per_unit")
        if self.state != FinancialInputState.PROVIDED and any(value is not None for value in costs):
            raise ValueError("missing or not_applicable COGS allocation must not carry costs")
        if any(value is not None and value < 0 for value in costs):
            raise ValueError("COGS allocation costs must be positive or zero")
        return self


class UnresolvedCogsEventInput(BaseModel):
    """Source event retained without an inferred COGS reversal or allocation."""

    model_config = ConfigDict(frozen=True)

    event: UnresolvedCogsEvent
    source: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=300)
    source_endpoint: str = Field(min_length=1, max_length=300)
    operational_date: date
    financial_date: date | None = None


class FinancialInput(BaseModel):
    """Immutable period-level input boundary; it performs no financial calculation."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    operational_date: date
    currency: CanonicalCurrency
    reconciled_facts: tuple[ReconciliationResult, ...]
    components: tuple[FinancialComponentInput, ...]
    revenue_views: tuple[RevenueBasisInput, ...] = ()
    cogs_allocations: tuple[CogsAllocationInput, ...] = ()
    advertising_expenses: tuple[AdvertisingExpenseInput, ...] = ()
    finality: tuple[FinancialFinalityInput, ...] = ()
    financial_lag: bool = False
    unresolved_cogs_events: tuple[UnresolvedCogsEventInput, ...] = ()
    rebill_logistics: tuple[RebillLogisticsInput, ...] = ()
    rounding_policy: MoneyRoundingPolicy = MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT

    @model_validator(mode="after")
    def require_consistent_scope_date_and_component_keys(self) -> FinancialInput:
        rebill_record_ids = {item.source_record_id for item in self.rebill_logistics}
        if len(rebill_record_ids) != len(self.rebill_logistics):
            raise ValueError("a rebill source record requires exactly one expense classification")
        revenue_view_keys = {(item.basis, item.source_record_id) for item in self.revenue_views}
        if len(revenue_view_keys) != len(self.revenue_views):
            raise ValueError("a source record may contribute each revenue basis at most once")
        for fact in self.reconciled_facts:
            if fact.identity.scope != self.scope:
                raise ValueError("reconciled facts must share FinancialInput tenant/account scope")
            if self.operational_date not in fact.operational_dates:
                raise ValueError("reconciled facts must include FinancialInput operational_date")
        for component in self.components:
            if component.operational_date != self.operational_date:
                raise ValueError("component operational_date must match FinancialInput operational_date")
        for revenue_view in self.revenue_views:
            if revenue_view.operational_date != self.operational_date:
                raise ValueError("revenue view operational_date must match FinancialInput operational_date")
        for finality in self.finality:
            if finality.operational_date != self.operational_date:
                raise ValueError("finality operational_date must match FinancialInput operational_date")
        for rebill in self.rebill_logistics:
            if rebill.operational_date != self.operational_date:
                raise ValueError("rebill operational_date must match FinancialInput operational_date")
        for event in self.unresolved_cogs_events:
            if event.operational_date != self.operational_date:
                raise ValueError("unresolved COGS event operational_date must match FinancialInput operational_date")
        return self


class FinancialComponentTrace(BaseModel):
    """Explainable result component retaining calculation inputs, without correction."""

    model_config = ConfigDict(frozen=True)

    component: FinancialComponent
    status: FinancialComponentStatus
    source_components: tuple[FinancialComponentInput, ...]
    source_cogs_allocations: tuple[CogsAllocationInput, ...] = ()
    source_advertising_expenses: tuple[AdvertisingExpenseInput, ...] = ()
    source_rebill_logistics: tuple[RebillLogisticsInput, ...] = ()
    source_cogs_events: tuple[UnresolvedCogsEventInput, ...] = ()
    amount: Decimal | None = None
    included: bool | None = None
    reason: str = Field(default="source component retained", min_length=1, max_length=500)

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("financial trace amount must not be float")
        return value

    @model_validator(mode="after")
    def require_trace_to_preserve_input_state(self) -> FinancialComponentTrace:
        included = self.included
        if included is None:
            included = self.status == FinancialComponentStatus.AVAILABLE
            object.__setattr__(self, "included", included)
        sources = (
            len(self.source_components)
            + len(self.source_cogs_allocations)
            + len(self.source_advertising_expenses)
            + len(self.source_rebill_logistics)
            + len(self.source_cogs_events)
        )
        if self.status == FinancialComponentStatus.AVAILABLE:
            if self.amount is None or sources == 0 or not included:
                raise ValueError("available trace requires an included amount and source inputs")
            if any(item.state != FinancialInputState.PROVIDED for item in self.source_components):
                raise ValueError("available trace may contain only provided source components")
        elif self.status == FinancialComponentStatus.UNRESOLVED:
            if sources == 0 or included:
                raise ValueError("unresolved trace requires excluded source inputs")
        elif self.status == FinancialComponentStatus.CONFLICT:
            if sources == 0 or included:
                raise ValueError("conflict trace requires excluded source inputs")
        elif self.amount is not None or included:
            raise ValueError("missing, not_applicable, or conflict trace must be excluded without an amount")
        return self


class UnitEconomicsResult(BaseModel):
    """Separate future SKU/unit read model; it is not a period P&L calculation."""

    model_config = ConfigDict(frozen=True)

    nm_id: str = Field(min_length=1, max_length=30)
    quantity: int = Field(gt=0)
    currency: CanonicalCurrency
    revenue_per_unit: Decimal | None = None
    cogs_per_unit: Decimal | None = None
    marketplace_deductions_per_unit: Decimal | None = None
    profit_per_unit: Decimal | None = None
    margin_per_unit: Decimal | None = None

    @field_validator(
        "revenue_per_unit",
        "cogs_per_unit",
        "marketplace_deductions_per_unit",
        "profit_per_unit",
        "margin_per_unit",
        mode="before",
    )
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("unit economics values must not be float")
        return value


class FinancialResult(BaseModel):
    """Immutable output contract for the constrained Finance Kernel Core."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    operational_date: date
    financial_dates: tuple[date, ...]
    currency: CanonicalCurrency
    status: FinancialStatus
    rounding_policy: MoneyRoundingPolicy
    component_traces: tuple[FinancialComponentTrace, ...]
    net_profit: Decimal | None = None
    profit_margin: Decimal | None = None
    diagnostics: tuple[str, ...] = ()

    @field_validator("net_profit", "profit_margin", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("FinancialResult values must not be float")
        return value

    @model_validator(mode="after")
    def require_unique_trace_components_and_status_consistency(self) -> FinancialResult:
        trace_components = {trace.component for trace in self.component_traces}
        if len(trace_components) != len(self.component_traces):
            raise ValueError("FinancialResult may contain one trace per component")
        if tuple(sorted(set(self.financial_dates))) != self.financial_dates:
            raise ValueError("financial_dates must be unique and sorted")
        if self.status == FinancialStatus.AWAITING_FINANCIAL_CONFIRMATION and self.financial_dates:
            raise ValueError("awaiting financial confirmation cannot include financial dates")
        if self.status in {
            FinancialStatus.PARTIAL,
            FinancialStatus.AWAITING_FINANCIAL_CONFIRMATION,
            FinancialStatus.CONFLICT,
            FinancialStatus.INSUFFICIENT_DATA,
        } and self.net_profit is not None:
            raise ValueError("non-complete result must not claim net_profit")
        if self.status == FinancialStatus.COMPLETE and self.net_profit is None:
            raise ValueError("complete result requires net_profit")
        if self.net_profit is None and self.profit_margin is not None:
            raise ValueError("profit_margin requires net_profit")
        return self
