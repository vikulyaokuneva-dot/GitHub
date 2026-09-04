"""Pure deterministic Finance Kernel Core."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from datetime import date
from typing import Final, Iterable

from packages.reconciliation.contracts import ReconciliationLagState

from .contracts import (
    AdvertisingAttribution,
    AdvertisingExpenseInput,
    CogsAllocationInput,
    FinancialComponent,
    FinancialComponentInput,
    FinancialComponentStatus,
    FinancialComponentTrace,
    FinancialFinality,
    FinancialInput,
    FinancialInputState,
    FinancialResult,
    FinancialStatus,
    RebillLogisticsInput,
    UnresolvedCogsEventInput,
)

_CENT: Final = Decimal("0.01")
_PERCENT: Final = Decimal("100")


def _trace_for_components(
    component: FinancialComponent,
    inputs: tuple[FinancialComponentInput, ...],
) -> FinancialComponentTrace:
    provided = tuple(item for item in inputs if item.state == FinancialInputState.PROVIDED)
    unresolved = tuple(item for item in inputs if item.state == FinancialInputState.UNRESOLVED)
    missing = tuple(item for item in inputs if item.state == FinancialInputState.MISSING)
    if unresolved:
        return FinancialComponentTrace(
            component=component,
            status=FinancialComponentStatus.UNRESOLVED,
            source_components=unresolved,
            amount=sum((item.amount for item in unresolved if item.amount is not None), Decimal("0")),
            included=False,
            reason="component unresolved; excluded from authoritative P&L",
        )
    if provided:
        amount = sum((item.amount for item in provided if item.amount is not None), Decimal("0"))
        return FinancialComponentTrace(
            component=component,
            status=FinancialComponentStatus.AVAILABLE,
            source_components=provided,
            amount=amount,
            included=True,
            reason="provided signed components included once",
        )
    if missing:
        return FinancialComponentTrace(
            component=component,
            status=FinancialComponentStatus.MISSING,
            source_components=missing,
            included=False,
            reason="component is missing; missing is not zero",
        )
    return FinancialComponentTrace(
        component=component,
        status=FinancialComponentStatus.NOT_APPLICABLE,
        source_components=inputs,
        included=False,
        reason="component is explicitly not applicable",
    )


def _cogs_trace(
    direct: tuple[FinancialComponentInput, ...],
    allocations: tuple[CogsAllocationInput, ...],
    *,
    unresolved_events: tuple[UnresolvedCogsEventInput, ...],
) -> FinancialComponentTrace:
    provided_direct = tuple(item for item in direct if item.state == FinancialInputState.PROVIDED)
    provided_allocations = tuple(
        item for item in allocations if item.state == FinancialInputState.PROVIDED and item.unit_cogs is not None
    )
    if provided_direct and provided_allocations:
        return FinancialComponentTrace(
            component=FinancialComponent.COGS,
            status=FinancialComponentStatus.CONFLICT,
            source_components=provided_direct,
            source_cogs_allocations=provided_allocations,
            included=False,
            reason="direct period COGS conflicts with unit-derived COGS",
        )
    if provided_direct:
        return _trace_for_components(FinancialComponent.COGS, direct)
    if provided_allocations:
        amount = -sum((item.unit_cogs * item.quantity for item in provided_allocations if item.unit_cogs is not None), Decimal("0"))
        return FinancialComponentTrace(
            component=FinancialComponent.COGS,
            status=FinancialComponentStatus.AVAILABLE,
            source_components=(),
            source_cogs_allocations=provided_allocations,
            amount=amount,
            included=True,
            reason="explicit unit COGS multiplied by caller-authoritative realized quantity",
        )
    if unresolved_events:
        return FinancialComponentTrace(
            component=FinancialComponent.COGS,
            status=FinancialComponentStatus.UNRESOLVED,
            source_components=direct,
            source_cogs_allocations=allocations,
            source_cogs_events=unresolved_events,
            included=False,
            reason="return or cancellation COGS treatment unresolved; no automatic reversal or allocation",
        )
    if direct:
        return _trace_for_components(FinancialComponent.COGS, direct)
    return FinancialComponentTrace(
        component=FinancialComponent.COGS,
        status=FinancialComponentStatus.MISSING,
        source_components=(),
        source_cogs_allocations=allocations,
        included=False,
        reason="explicit Product Economics COGS input is missing",
    )


def _advertising_trace(expenses: tuple[AdvertisingExpenseInput, ...]) -> FinancialComponentTrace | None:
    if not expenses:
        return None
    amount = sum((item.amount for item in expenses), Decimal("0"))
    has_unallocated_sku_cost = any(
        item.attribution != AdvertisingAttribution.DIRECT and item.nm_id is not None for item in expenses
    )
    if has_unallocated_sku_cost:
        raise AssertionError("advertising contract admitted unsupported SKU attribution")
    reason = "period advertising included without automatic SKU allocation"
    if all(item.attribution == AdvertisingAttribution.DIRECT for item in expenses):
        reason = "direct advertising included with evidenced nm_id attribution"
    return FinancialComponentTrace(
        component=FinancialComponent.ADVERTISING,
        status=FinancialComponentStatus.AVAILABLE,
        source_components=(),
        source_advertising_expenses=expenses,
        amount=amount,
        included=True,
        reason=reason,
    )


def _rebill_trace(rebills: tuple[RebillLogisticsInput, ...]) -> FinancialComponentTrace | None:
    if not rebills:
        return None
    return FinancialComponentTrace(
        component=FinancialComponent.REBILL_LOGISTICS,
        status=FinancialComponentStatus.UNRESOLVED,
        source_components=(),
        source_rebill_logistics=rebills,
        amount=sum((item.amount for item in rebills), Decimal("0")),
        included=False,
        reason="rebillLogisticCost classification unresolved; excluded from authoritative P&L",
    )


def _duplicates(financial_input: FinancialInput) -> tuple[str, ...]:
    keys: list[tuple[str, str]] = [
        (item.component.value, item.source_record_id) for item in financial_input.components
    ]
    keys.extend((FinancialComponent.COGS.value, item.source_record_id) for item in financial_input.cogs_allocations)
    keys.extend((FinancialComponent.ADVERTISING.value, item.source_record_id) for item in financial_input.advertising_expenses)
    keys.extend((FinancialComponent.REBILL_LOGISTICS.value, item.source_record_id) for item in financial_input.rebill_logistics)
    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for key in keys:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(f"duplicate source component: {component}:{source_record_id}" for component, source_record_id in sorted(duplicates))


def _financial_dates(financial_input: FinancialInput) -> tuple[date, ...]:
    values = {item.financial_date for item in financial_input.components if item.financial_date is not None}
    values.update(item.financial_date for item in financial_input.finality if item.financial_date is not None)
    values.update(item.financial_date for item in financial_input.rebill_logistics if item.financial_date is not None)
    values.update(item.financial_date for item in financial_input.unresolved_cogs_events if item.financial_date is not None)
    return tuple(sorted(values))


def _status(
    financial_input: FinancialInput,
    traces: Iterable[FinancialComponentTrace],
    duplicate_diagnostics: tuple[str, ...],
    *,
    has_financial_dates: bool,
) -> FinancialStatus:
    trace_tuple = tuple(traces)
    if duplicate_diagnostics or any(trace.status == FinancialComponentStatus.CONFLICT for trace in trace_tuple):
        return FinancialStatus.CONFLICT
    revenue = next((trace for trace in trace_tuple if trace.component == FinancialComponent.REALIZED_REVENUE), None)
    if revenue is None or revenue.status != FinancialComponentStatus.AVAILABLE:
        awaiting_confirmation = bool(financial_input.reconciled_facts) and any(
            fact.lag_state == ReconciliationLagState.AWAITING_FINANCIAL_CONFIRMATION
            for fact in financial_input.reconciled_facts
        )
        if awaiting_confirmation and not has_financial_dates:
            return FinancialStatus.AWAITING_FINANCIAL_CONFIRMATION
        return FinancialStatus.INSUFFICIENT_DATA
    has_final_evidence = bool(financial_input.finality) and all(
        item.finality == FinancialFinality.FINAL for item in financial_input.finality
    )
    incomplete = any(
        trace.status in {FinancialComponentStatus.MISSING, FinancialComponentStatus.UNRESOLVED}
        for trace in trace_tuple
    )
    return FinancialStatus.COMPLETE if has_final_evidence and not financial_input.financial_lag and not incomplete else FinancialStatus.PARTIAL


def calculate_financial_result(financial_input: FinancialInput) -> FinancialResult:
    """Calculate one immutable period result from explicit signed inputs."""

    grouped: dict[FinancialComponent, list[FinancialComponentInput]] = {}
    for item in financial_input.components:
        grouped.setdefault(item.component, []).append(item)

    traces: list[FinancialComponentTrace] = []
    for component in FinancialComponent:
        if component in {FinancialComponent.COGS, FinancialComponent.ADVERTISING, FinancialComponent.REBILL_LOGISTICS}:
            continue
        inputs = tuple(grouped.get(component, ()))
        if inputs:
            traces.append(_trace_for_components(component, inputs))

    if FinancialComponent.TAX not in grouped:
        traces.append(
            FinancialComponentTrace(
                component=FinancialComponent.TAX,
                status=FinancialComponentStatus.MISSING,
                source_components=(),
                included=False,
                reason="sourced tax input is absent; missing tax is not zero",
            )
        )

    cogs = _cogs_trace(
        tuple(grouped.get(FinancialComponent.COGS, ())),
        financial_input.cogs_allocations,
        unresolved_events=financial_input.unresolved_cogs_events,
    )
    traces.append(cogs)

    direct_advertising = tuple(grouped.get(FinancialComponent.ADVERTISING, ()))
    if direct_advertising and financial_input.advertising_expenses:
        traces.append(
            FinancialComponentTrace(
                component=FinancialComponent.ADVERTISING,
                status=FinancialComponentStatus.CONFLICT,
                source_components=direct_advertising,
                source_advertising_expenses=financial_input.advertising_expenses,
                included=False,
                reason="generic and attributed advertising inputs conflict",
            )
        )
    elif direct_advertising:
        traces.append(_trace_for_components(FinancialComponent.ADVERTISING, direct_advertising))
    else:
        advertising = _advertising_trace(financial_input.advertising_expenses)
        if advertising is not None:
            traces.append(advertising)

    rebill_component = tuple(grouped.get(FinancialComponent.REBILL_LOGISTICS, ()))
    if rebill_component:
        traces.append(_trace_for_components(FinancialComponent.REBILL_LOGISTICS, rebill_component))
    else:
        rebill = _rebill_trace(financial_input.rebill_logistics)
        if rebill is not None:
            traces.append(rebill)

    traces.sort(key=lambda trace: trace.component.value)
    duplicate_diagnostics = _duplicates(financial_input)
    financial_dates = _financial_dates(financial_input)
    status = _status(
        financial_input,
        traces,
        duplicate_diagnostics,
        has_financial_dates=bool(financial_dates),
    )
    diagnostics = list(duplicate_diagnostics)
    diagnostics.extend(trace.reason for trace in traces if trace.status in {FinancialComponentStatus.UNRESOLVED, FinancialComponentStatus.CONFLICT})

    net_profit: Decimal | None = None
    margin: Decimal | None = None
    if status == FinancialStatus.COMPLETE:
        aggregate = sum((trace.amount for trace in traces if trace.included and trace.amount is not None), Decimal("0"))
        net_profit = aggregate.quantize(_CENT, rounding=ROUND_HALF_UP)
        revenue = next(trace.amount for trace in traces if trace.component == FinancialComponent.REALIZED_REVENUE)
        if revenue is not None and revenue != 0:
            margin = ((net_profit / revenue) * _PERCENT).quantize(_CENT, rounding=ROUND_HALF_UP)

    return FinancialResult(
        scope=financial_input.scope,
        operational_date=financial_input.operational_date,
        financial_dates=financial_dates,
        currency=financial_input.currency,
        status=status,
        rounding_policy=financial_input.rounding_policy,
        component_traces=tuple(traces),
        net_profit=net_profit,
        profit_margin=margin,
        diagnostics=tuple(diagnostics),
    )
