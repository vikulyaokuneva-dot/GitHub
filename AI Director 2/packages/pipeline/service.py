"""Orchestrate persisted raw objects through canonical domains into a report payload."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from packages.advertising.service import build_advertising_read_model
from packages.data.canonical import CanonicalFinanceDetailRecord, CanonicalOperationalSale
from packages.data.normalization import (
    normalize_advertising_performance,
    normalize_finance_detail,
    normalize_orders,
    normalize_sales,
    normalize_sales_funnel_products,
    normalize_stocks,
)
from packages.finance.contracts import (
    CogsAllocationInput,
    FinancialComponentInput,
    FinancialFinalityInput,
)
from packages.finance.flow import (
    IntegratedFinancialFlowResult,
    calculate_integrated_financial_flow,
)
from packages.operational.contracts import OperationalDailyReadModel
from packages.operational.service import (
    build_empty_operational_daily_read_model,
    build_operational_daily_read_model,
)
from packages.products.contracts import DirectPeriodCogsInput, ProductCostProfile
from packages.products.service import to_cogs_allocation
from packages.reconciliation.contracts import ReconciliationResult
from packages.reconciliation.service import reconcile_sales_funnel_products
from packages.reports.contracts import ReportPayload
from packages.reports.service import build_report_payload
from packages.settings.contracts import FinancialSettings
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import (
    RawObject,
    RawObjectRepository,
    RawObjectType,
    TenantAccountScope,
)


class PipelineResult(BaseModel):
    """Immutable output of the target pipeline with no hidden runtime inputs."""

    model_config = ConfigDict(frozen=True)

    operational: OperationalDailyReadModel
    reconciled_facts: tuple[ReconciliationResult, ...]
    finance_records: tuple[CanonicalFinanceDetailRecord, ...]
    financial_flow: IntegratedFinancialFlowResult
    report_payload: ReportPayload


def _by_type(
    raw_objects: tuple[RawObject, ...],
    object_type: RawObjectType,
) -> tuple[RawObject, ...]:
    """Return only persisted raw objects of the requested type."""
    return tuple(
        item
        for item in raw_objects
        if item.object_type == object_type
    )


def _validate_scope(
    *,
    raw_objects: tuple[RawObject, ...],
    scope: TenantAccountScope,
) -> None:
    """Prevent accidental cross-account/cross-tenant pipeline execution."""

    for raw_object in raw_objects:
        if raw_object.scope != scope:
            raise ValueError(
                "pipeline raw objects must share a tenant/account scope"
            )


def _source_counts(
    raw_objects: tuple[RawObject, ...],
) -> dict[str, int]:
    """Return persisted raw-object counts by canonical object type."""

    return {
        object_type.value: sum(
            1
            for raw_object in raw_objects
            if raw_object.object_type == object_type
        )
        for object_type in RawObjectType
    }


def _cogs_allocations(
    *,
    profiles: tuple[ProductCostProfile, ...],
    sales: tuple[CanonicalOperationalSale, ...],
    operational_date: date,
) -> tuple[tuple[CogsAllocationInput, ...], tuple[str, ...]]:
    """Pair each declared unit cost with the authoritative realized quantity.

    A sold item without a declared cost produces a diagnostic instead of a
    silent gap, and a sale without a usable positive quantity produces no
    allocation at all: absence is never priced as zero.
    """

    if not profiles:
        return (), ()

    quantities: dict[str, Decimal] = {}
    for record in sales:
        if record.nm_id is None or record.quantity is None or record.quantity <= 0:
            continue
        quantities[record.nm_id] = quantities.get(record.nm_id, Decimal("0")) + record.quantity

    priced: dict[str, ProductCostProfile] = {profile.nm_id: profile for profile in profiles}
    allocations: list[CogsAllocationInput] = []
    diagnostics: list[str] = []
    for nm_id, quantity in sorted(quantities.items()):
        profile = priced.get(nm_id)
        if profile is None:
            diagnostics.append(f"unit cost is not declared for sold nm_id {nm_id}")
            continue
        if profile.unit_cogs is None:
            diagnostics.append(f"unit cost is unavailable for sold nm_id {nm_id}")
            continue
        if not quantity.to_integral_value() == quantity:
            diagnostics.append(f"realized quantity for nm_id {nm_id} is fractional; unit COGS was not applied")
            continue
        allocations.append(to_cogs_allocation(profile, quantity=int(quantity), operational_date=operational_date))
    return tuple(allocations), tuple(diagnostics)


def run_pipeline(
    *,
    repository: RawObjectRepository,
    raw_objects: tuple[RawObject, ...],
    finality: tuple[FinancialFinalityInput, ...] = (),
    period_cogs: DirectPeriodCogsInput | None = None,
    tax: SourcedTaxInput | None = None,
    unresolved_marketplace_components: tuple[
        FinancialComponentInput, ...
    ] = (),
    financial_lag: bool = False,
    financial_settings: FinancialSettings | None = None,
) -> PipelineResult:
    """
    Run the target path from supplied raw objects only.

    This function is primarily useful for fixtures/replay.
    It performs no WB API calls.
    """

    if not raw_objects:
        raise ValueError("pipeline requires at least one raw object")

    scope = raw_objects[0].scope

    _validate_scope(
        raw_objects=raw_objects,
        scope=scope,
    )

    for raw_object in raw_objects:
        repository.save(raw_object)

    return _run_raw_objects(
        scope=scope,
        operational_date=raw_objects[0].operational_date,
        raw_objects=raw_objects,
        finality=finality,
        period_cogs=period_cogs,
        tax=tax,
        unresolved_marketplace_components=(
            unresolved_marketplace_components
        ),
        financial_lag=financial_lag,
        financial_settings=financial_settings,
    )


def run_stored_daily_pipeline(
    *,
    repository: RawObjectRepository,
    scope: TenantAccountScope,
    operational_date: date,
    finality: tuple[FinancialFinalityInput, ...] = (),
    period_cogs: DirectPeriodCogsInput | None = None,
    tax: SourcedTaxInput | None = None,
    unresolved_marketplace_components: tuple[
        FinancialComponentInput, ...
    ] = (),
    financial_lag: bool = False,
    financial_settings: FinancialSettings | None = None,
) -> PipelineResult:
    """
    Run one tenant day from already durable RawObjects.

    IMPORTANT:
        This function never calls WB.
        It never performs ingestion.
        It never writes new RawObjects.

    The caller is responsible for ensuring that live ingestion has already
    completed.
    """

    raw_objects = tuple(
        item
        for item in repository.list(scope=scope)
        if item.operational_date == operational_date
    )

    return _run_raw_objects(
        scope=scope,
        operational_date=operational_date,
        raw_objects=raw_objects,
        finality=finality,
        period_cogs=period_cogs,
        tax=tax,
        unresolved_marketplace_components=(
            unresolved_marketplace_components
        ),
        financial_lag=financial_lag,
        financial_settings=financial_settings,
    )


def _run_raw_objects(
    *,
    scope: TenantAccountScope,
    operational_date: date | None,
    raw_objects: tuple[RawObject, ...],
    finality: tuple[FinancialFinalityInput, ...],
    period_cogs: DirectPeriodCogsInput | None,
    tax: SourcedTaxInput | None,
    unresolved_marketplace_components: tuple[
        FinancialComponentInput, ...
    ],
    financial_lag: bool,
    financial_settings: FinancialSettings | None = None,
) -> PipelineResult:
    """Transform persisted RawObjects into the final report payload."""

    if operational_date is None:
        raise ValueError(
            "pipeline raw objects require an operational date"
        )

    _validate_scope(
        raw_objects=raw_objects,
        scope=scope,
    )

    # ================================================================
    # OPERATIONAL DOMAIN
    # ================================================================

    orders = tuple(
        record
        for raw in _by_type(
            raw_objects,
            RawObjectType.ORDERS,
        )
        for record in normalize_orders(raw)
    )

    sales = tuple(
        record
        for raw in _by_type(
            raw_objects,
            RawObjectType.SALES,
        )
        for record in normalize_sales(raw)
    )

    stocks = tuple(
        record
        for raw in _by_type(
            raw_objects,
            RawObjectType.STOCKS,
        )
        for record in normalize_stocks(raw)
    )

    funnel = tuple(
        record
        for raw in _by_type(
            raw_objects,
            RawObjectType.SALES_FUNNEL_PRODUCTS,
        )
        for record in normalize_sales_funnel_products(raw)
    )

    operational_facts = (
        *orders,
        *sales,
        *stocks,
        *funnel,
    )

    operational = (
        build_operational_daily_read_model(
            orders=orders,
            sales=sales,
            stock_snapshots=stocks,
            funnel_products=funnel,
        )
        if operational_facts
        else build_empty_operational_daily_read_model(
            scope=scope,
            operational_date=operational_date,
        )
    )

    # ================================================================
    # RECONCILIATION
    # ================================================================

    reconciled = reconcile_sales_funnel_products(funnel)

    # ================================================================
    # FINANCE DETAIL
    # ================================================================

    finance_records = tuple(
        record
        for raw in _by_type(
            raw_objects,
            RawObjectType.FINANCE_DETAIL,
        )
        for record in normalize_finance_detail(raw)
    )

    # ================================================================
    # ADVERTISING
    # ================================================================

    advertising_facts = tuple(
        record
        for raw in _by_type(
            raw_objects,
            RawObjectType.ADVERTISING_PERFORMANCE,
        )
        for record in normalize_advertising_performance(raw)
    )

    advertising = (
        build_advertising_read_model(advertising_facts)
        if advertising_facts
        else None
    )

    # ================================================================
    # USER-PROVIDED FINANCIAL PARAMETERS
    # ================================================================
    #
    # Seller declarations enter the pipeline as ordinary domain inputs.  The
    # Finance Kernel still owns every calculation; nothing here is defaulted.
    # ------------------------------------------------------------

    product_costs = (
        financial_settings.applicable_product_costs(operational_date)
        if financial_settings is not None
        else ()
    )
    cogs_allocations, cogs_diagnostics = _cogs_allocations(
        profiles=product_costs,
        sales=sales,
        operational_date=operational_date,
    )
    tax_rate = financial_settings.tax_rate if financial_settings is not None else None

    # ================================================================
    # INTEGRATED FINANCE
    # ================================================================

    financial_flow = calculate_integrated_financial_flow(
        finance_records=finance_records,
        finality=finality,
        advertising=advertising,
        period_cogs=period_cogs,
        tax=tax,
        cogs_allocations=cogs_allocations,
        tax_rate=tax_rate,
        reconciled_facts=reconciled,
        unresolved_marketplace_components=(
            unresolved_marketplace_components
        ),
        financial_lag=financial_lag,
    )

    # ================================================================
    # REPORT PAYLOAD
    # ================================================================

    report_diagnostics = list(financial_flow.diagnostics)
    report_diagnostics.extend(cogs_diagnostics)

    if financial_flow.financial_result is not None:
        report_diagnostics.extend(
            financial_flow.financial_result.diagnostics
        )

    report_payload = build_report_payload(
        operational=operational,
        financial=financial_flow.financial_result,
        advertising=advertising,
        diagnostics=tuple(report_diagnostics),
    )

    return PipelineResult(
        operational=operational,
        reconciled_facts=reconciled,
        finance_records=finance_records,
        financial_flow=financial_flow,
        report_payload=report_payload,
    )