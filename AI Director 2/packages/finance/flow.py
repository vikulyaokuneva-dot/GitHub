"""Integrated application flow for already-normalized financial domain inputs."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from packages.advertising.contracts import AdvertisingReadModel
from packages.data.canonical import AdvertisingAttributionScope, CanonicalFinanceDetailRecord
from packages.products.contracts import DirectPeriodCogsInput
from packages.products.service import to_financial_component as cogs_component
from packages.reconciliation.contracts import ReconciliationResult
from packages.tax.contracts import SourcedTaxInput, TaxRateSetting
from packages.tax.service import tax_input_from_rate
from packages.tax.service import to_financial_component as tax_component

from .contracts import (
    AdvertisingAttribution,
    AdvertisingExpenseInput,
    CogsAllocationInput,
    FinancialComponent,
    FinancialComponentInput,
    FinancialFinalityInput,
    FinancialInput,
    FinancialInputState,
    FinancialResult,
)
from .finance_detail_adapter import build_financial_input_from_finance_detail
from .kernel import calculate_financial_result
from .status import FinancialFinalityAssessment, assess_financial_finality


class IntegratedFinancialFlowResult(BaseModel):
    """End-to-end finance result with retained construction diagnostics."""

    model_config = ConfigDict(frozen=True)

    financial_input: FinancialInput | None = None
    financial_result: FinancialResult | None = None
    finality_assessment: FinancialFinalityAssessment | None = None
    diagnostics: tuple[str, ...] = ()


def _advertising_expenses(read_model: AdvertisingReadModel) -> tuple[tuple[AdvertisingExpenseInput, ...], tuple[str, ...]]:
    expenses: list[AdvertisingExpenseInput] = []
    diagnostics: list[str] = []
    for fact in read_model.facts:
        if fact.spend is None:
            diagnostics.append(f"advertising spend missing for {fact.source_metadata.source_object_id}:{fact.source_metadata.source_record_index}")
            continue
        if fact.spend < 0:
            diagnostics.append(
                f"advertising spend has unsupported negative source sign for "
                f"{fact.source_metadata.source_object_id}:{fact.source_metadata.source_record_index}"
            )
            continue
        attribution = (
            AdvertisingAttribution.DIRECT
            if fact.attribution_scope == AdvertisingAttributionScope.DIRECT_SKU
            else AdvertisingAttribution.PERIOD_LEVEL
            if fact.attribution_scope in {AdvertisingAttributionScope.CAMPAIGN, AdvertisingAttributionScope.PERIOD}
            else AdvertisingAttribution.UNKNOWN
        )
        expenses.append(
            AdvertisingExpenseInput(
                amount=-fact.spend,
                attribution=attribution,
                period_start=fact.operational_date,
                period_end=fact.operational_date,
                source=fact.source_metadata.source,
                source_record_id=f"{fact.source_metadata.source_object_id}:{fact.source_metadata.source_record_index}",
                campaign_id=fact.campaign_id,
                nm_id=fact.nm_id if attribution == AdvertisingAttribution.DIRECT else None,
            )
        )
    return tuple(expenses), tuple(diagnostics)


def _provided_realized_revenue(financial_input: FinancialInput) -> Decimal | None:
    """The evidenced realized-revenue base, or ``None`` when nothing was provided.

    ``None`` is not zero: a seller tax rate applied to an unevidenced base yields
    a missing tax rather than a free pass through the P&L.
    """

    provided = [
        item.amount
        for item in financial_input.components
        if item.component == FinancialComponent.REALIZED_REVENUE
        and item.state == FinancialInputState.PROVIDED
        and item.amount is not None
    ]
    if not provided:
        return None
    return sum(provided, Decimal("0"))


def calculate_integrated_financial_flow(
    *,
    finance_records: tuple[CanonicalFinanceDetailRecord, ...],
    finality: tuple[FinancialFinalityInput, ...] = (),
    advertising: AdvertisingReadModel | None = None,
    period_cogs: DirectPeriodCogsInput | None = None,
    tax: SourcedTaxInput | None = None,
    cogs_allocations: tuple[CogsAllocationInput, ...] = (),
    tax_rate: TaxRateSetting | None = None,
    reconciled_facts: tuple[ReconciliationResult, ...] = (),
    unresolved_marketplace_components: tuple[FinancialComponentInput, ...] = (),
    financial_lag: bool = False,
) -> IntegratedFinancialFlowResult:
    """Join migrated finance inputs without inferring marketplace deductions or COGS events."""

    detail_build = build_financial_input_from_finance_detail(finance_records)
    if detail_build.financial_input is None:
        return IntegratedFinancialFlowResult(diagnostics=detail_build.diagnostics)
    base = detail_build.financial_input
    diagnostics = list(detail_build.diagnostics)
    components = list(base.components)
    if tax is None and tax_rate is not None:
        if tax_rate.scope != base.scope:
            return IntegratedFinancialFlowResult(
                diagnostics=tuple(diagnostics + ["tax rate scope does not match finance detail"])
            )
        tax = tax_input_from_rate(
            tax_rate,
            operational_date=base.operational_date,
            realized_revenue=_provided_realized_revenue(base),
        )
    if period_cogs is not None:
        if period_cogs.scope != base.scope or period_cogs.operational_date != base.operational_date:
            return IntegratedFinancialFlowResult(diagnostics=tuple(diagnostics + ["period COGS scope/date does not match finance detail"]))
        components.append(cogs_component(period_cogs))
    if tax is not None:
        if tax.scope != base.scope or tax.operational_date != base.operational_date:
            return IntegratedFinancialFlowResult(diagnostics=tuple(diagnostics + ["tax scope/date does not match finance detail"]))
        components.append(tax_component(tax))
    for component in unresolved_marketplace_components:
        if component.component not in {
            FinancialComponent.MARKETPLACE_COMMISSION,
            FinancialComponent.LOGISTICS,
            FinancialComponent.REVERSE_LOGISTICS,
            FinancialComponent.ACQUIRING,
            FinancialComponent.ACCEPTANCE,
            FinancialComponent.OTHER_MARKETPLACE_DEDUCTIONS,
            FinancialComponent.REBILL_LOGISTICS,
        } or component.state != FinancialInputState.UNRESOLVED:
            return IntegratedFinancialFlowResult(
                diagnostics=tuple(diagnostics + ["only unresolved marketplace components may enter the Stage 15 flow"])
            )
        components.append(component)
    advertising_expenses: tuple[AdvertisingExpenseInput, ...] = ()
    if advertising is not None:
        advertising_expenses, advertising_diagnostics = _advertising_expenses(advertising)
        diagnostics.extend(advertising_diagnostics)
    selected_finality = finality or base.finality
    if any(item.identity.scope != base.scope or base.operational_date not in item.operational_dates for item in reconciled_facts):
        return IntegratedFinancialFlowResult(
            diagnostics=tuple(diagnostics + ["reconciled operational facts do not match finance detail scope/date"])
        )
    finality_assessment = assess_financial_finality(
        selected_finality,
        has_financial_facts=bool(base.components),
        financial_lag=financial_lag,
    )
    financial_input = FinancialInput(
        scope=base.scope,
        operational_date=base.operational_date,
        currency=base.currency,
        reconciled_facts=reconciled_facts,
        components=tuple(components),
        revenue_views=base.revenue_views,
        cogs_allocations=base.cogs_allocations + tuple(cogs_allocations),
        advertising_expenses=advertising_expenses,
        finality=selected_finality,
        financial_lag=financial_lag,
        unresolved_cogs_events=base.unresolved_cogs_events,
        rebill_logistics=base.rebill_logistics,
        rounding_policy=base.rounding_policy,
    )
    result = calculate_financial_result(financial_input)
    return IntegratedFinancialFlowResult(
        financial_input=financial_input,
        financial_result=result,
        finality_assessment=finality_assessment,
        diagnostics=tuple(diagnostics),
    )
