"""Financial metrics assembler foundation.

Input: NormalizedBundle.
Output: FinancialMetricsSection.
Does not compute full KPI universe and does not render outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ...core.contracts import (
    FinancialMetricsSection,
    MetricStatus,
    MetricValue,
    NormalizedBundle,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
)
from .lag_fallback import resolve_realization_window


USABLE_SOURCE_STATES = {"ok", "partial"}


@dataclass(frozen=True)
class _AmountAggregate:
    value: float | None
    has_data: bool
    has_missing: bool


def _metric(
    value: float | int | None,
    *,
    status: MetricStatus,
    source: str | None,
    note: str | None = None,
) -> MetricValue:
    return MetricValue(value=value, status=status.value, source=source, note=note)


def _source_state(bundle: NormalizedBundle, source_name: str) -> str:
    status = bundle.source_statuses.get(source_name)
    if status is None:
        return "missing"
    raw_state = getattr(status, "status", None)
    if raw_state is None:
        return "missing"
    if hasattr(raw_state, "value"):
        return str(raw_state.value)
    text = str(raw_state).strip().lower()
    return text or "missing"


def _source_usable(state: str) -> bool:
    return state in USABLE_SOURCE_STATES


def _target_date(bundle: NormalizedBundle) -> str | None:
    return bundle.run_context.resolved_date_iso or bundle.run_context.requested_date_iso


def _filter_by_date(records: Iterable, getter, target_date: str | None) -> list:
    if not target_date:
        return list(records)
    out = []
    for record in records:
        if getter(record) == target_date:
            out.append(record)
    return out


def _base_status(source_state: str, *, forced_partial: bool = False) -> MetricStatus:
    if not _source_usable(source_state):
        return MetricStatus.UNAVAILABLE
    if forced_partial or source_state == "partial":
        return MetricStatus.PARTIAL
    return MetricStatus.CONFIRMED


def _is_return_sale(record: NormalizedSaleRecord) -> bool | None:
    if record.is_return is not None:
        return bool(record.is_return)
    text = str(record.operation_type or "").strip().lower()
    if not text:
        return None
    if "возврат" in text or "return" in text:
        return True
    if "продаж" in text or "sale" in text or "реализац" in text:
        return False
    return None


def _aggregate_amount(values: list[float | None]) -> _AmountAggregate:
    has_missing = any(value is None for value in values)
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return _AmountAggregate(value=None, has_data=False, has_missing=has_missing)
    return _AmountAggregate(value=round(sum(numeric), 2), has_data=True, has_missing=has_missing)


def _metric_from_count(
    *,
    count: int | None,
    source_state: str,
    source: str,
    forced_partial: bool = False,
    note: str | None = None,
) -> MetricValue:
    status = _base_status(source_state, forced_partial=forced_partial)
    if status == MetricStatus.UNAVAILABLE:
        return _metric(None, status=status, source=source, note=note)
    return _metric(int(count or 0), status=status, source=source, note=note)


def _metric_from_amount(
    *,
    values: list[float | None],
    source_state: str,
    source: str,
    forced_partial: bool = False,
    empty_zero_if_source_usable: bool = False,
    note_if_missing: str | None = None,
) -> MetricValue:
    status = _base_status(source_state, forced_partial=forced_partial)
    if status == MetricStatus.UNAVAILABLE:
        return _metric(None, status=status, source=source, note=note_if_missing)

    if not values:
        if empty_zero_if_source_usable:
            return _metric(0.0, status=status, source=source, note=None)
        return _metric(None, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)

    agg = _aggregate_amount(values)
    if agg.has_data:
        if agg.has_missing or status == MetricStatus.PARTIAL:
            return _metric(agg.value, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)
        return _metric(agg.value, status=MetricStatus.CONFIRMED, source=source, note=None)

    if empty_zero_if_source_usable and not agg.has_missing:
        return _metric(0.0, status=status, source=source, note=None)

    return _metric(None, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)


def _event_values(records: list[NormalizedRealizationRecord], event_type: str) -> list[float | None]:
    return [record.amount for record in records if record.event_type == event_type]


def _overall_financial_status(metrics: list[MetricValue]) -> str:
    if not metrics:
        return MetricStatus.UNAVAILABLE.value
    states = {metric.status for metric in metrics}
    if states == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in states or MetricStatus.PARTIAL.value in states:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def assemble_financial_metrics(normalized_bundle: NormalizedBundle) -> FinancialMetricsSection:
    """Assemble conservative financial metrics from normalized records.

    Counting rule used on this stage:
    - orders_count, sales_count, returns_count are record-based counts,
      not quantity sums. This keeps behavior stable when quantity quality
      is source-dependent.
    """

    target_date = _target_date(normalized_bundle)
    source_orders = _source_state(normalized_bundle, "orders")
    source_sales = _source_state(normalized_bundle, "sales")
    source_realization = _source_state(normalized_bundle, "realization")

    orders_for_day = _filter_by_date(normalized_bundle.orders, lambda row: row.order_date, target_date)
    sales_for_day = _filter_by_date(normalized_bundle.sales, lambda row: row.sale_date, target_date)

    return_rows = [row for row in sales_for_day if _is_return_sale(row) is True]
    sale_rows = [row for row in sales_for_day if _is_return_sale(row) is False]

    resolution = resolve_realization_window(normalized_bundle, normalized_bundle.run_context)
    realization_for_day = _filter_by_date(
        normalized_bundle.realization,
        lambda row: row.event_date,
        resolution.actual_date,
    ) if resolution.actual_date else []

    warnings = list(resolution.warnings)

    orders_count = _metric_from_count(
        count=len(orders_for_day),
        source_state=source_orders,
        source="orders",
    )

    orders_amount_values: list[float | None] = []
    for row in orders_for_day:
        if row.price is None:
            orders_amount_values.append(None)
            continue
        qty = float(row.quantity) if row.quantity is not None else 1.0
        orders_amount_values.append(float(row.price) * qty)

    orders_amount = _metric_from_amount(
        values=orders_amount_values,
        source_state=source_orders,
        source="orders",
        empty_zero_if_source_usable=True,
        note_if_missing="orders amount is partially unavailable",
    )

    if _source_usable(source_sales):
        sales_count = _metric_from_count(
            count=len(sale_rows),
            source_state=source_sales,
            source="sales",
        )
        returns_count = _metric_from_count(
            count=len(return_rows),
            source_state=source_sales,
            source="sales",
        )

        sales_amount = _metric_from_amount(
            values=[row.sale_amount for row in sale_rows],
            source_state=source_sales,
            source="sales",
            empty_zero_if_source_usable=True,
            note_if_missing="sales amount is partially unavailable",
        )
    else:
        sale_events = [row for row in realization_for_day if row.event_type == "sale"]
        return_events = [row for row in realization_for_day if row.event_type == "return"]
        forced_partial = bool(sale_events or return_events)

        sales_count = _metric_from_count(
            count=len(sale_events) if forced_partial else None,
            source_state=source_realization,
            source="realization",
            forced_partial=forced_partial,
            note=("derived from realization events" if forced_partial else "sales source unavailable"),
        )
        returns_count = _metric_from_count(
            count=len(return_events) if forced_partial else None,
            source_state=source_realization,
            source="realization",
            forced_partial=forced_partial,
            note=("derived from realization events" if forced_partial else "sales source unavailable"),
        )
        sales_amount = _metric_from_amount(
            values=[row.amount for row in sale_events],
            source_state=source_realization,
            source="realization",
            forced_partial=forced_partial,
            empty_zero_if_source_usable=forced_partial,
            note_if_missing="sales amount derived from realization is unavailable",
        )
        warnings.append("sales source unavailable: fallback to realization-derived sales subset")

    realization_for_metrics_available = _source_usable(source_realization) and resolution.actual_date is not None
    realization_for_metrics_state = source_realization if realization_for_metrics_available else "missing"

    payout_from_realization = [
        row.amount
        for row in realization_for_day
        if row.event_type in {"sale", "return"}
    ]
    seller_payout = _metric_from_amount(
        values=payout_from_realization,
        source_state=realization_for_metrics_state,
        source="realization",
        forced_partial=bool(resolution.fallback_used),
        empty_zero_if_source_usable=False,
        note_if_missing="seller payout is unavailable in realization records",
    )

    if seller_payout.value is None and _source_usable(source_sales):
        seller_payout = _metric_from_amount(
            values=[row.payout_amount for row in sale_rows],
            source_state=source_sales,
            source="sales",
            forced_partial=True,
            empty_zero_if_source_usable=False,
            note_if_missing="seller payout is unavailable",
        )

    logistics_cost = _metric_from_amount(
        values=_event_values(realization_for_day, "logistics"),
        source_state=realization_for_metrics_state,
        source="realization",
        forced_partial=bool(resolution.fallback_used),
        empty_zero_if_source_usable=True,
        note_if_missing="logistics cost is unavailable",
    )
    storage_cost = _metric_from_amount(
        values=_event_values(realization_for_day, "storage"),
        source_state=realization_for_metrics_state,
        source="realization",
        forced_partial=bool(resolution.fallback_used),
        empty_zero_if_source_usable=True,
        note_if_missing="storage cost is unavailable",
    )
    deductions_amount = _metric_from_amount(
        values=_event_values(realization_for_day, "deduction"),
        source_state=realization_for_metrics_state,
        source="realization",
        forced_partial=bool(resolution.fallback_used),
        empty_zero_if_source_usable=True,
        note_if_missing="deductions amount is unavailable",
    )

    components = [sales_amount, logistics_cost, storage_cost, deductions_amount]
    if any(metric.status == MetricStatus.UNAVAILABLE.value for metric in components):
        net_realization_amount = _metric(
            None,
            status=MetricStatus.UNAVAILABLE,
            source="financial_formula_v1",
            note="insufficient components for net realization",
        )
    elif any(metric.value is None for metric in components):
        net_realization_amount = _metric(
            None,
            status=MetricStatus.PARTIAL,
            source="financial_formula_v1",
            note="partial components for net realization",
        )
    else:
        net_value = (
            float(sales_amount.value)
            - float(logistics_cost.value)
            - float(storage_cost.value)
            - float(deductions_amount.value)
        )
        net_status = MetricStatus.CONFIRMED
        if any(metric.status != MetricStatus.CONFIRMED.value for metric in components):
            net_status = MetricStatus.PARTIAL
        net_realization_amount = _metric(
            round(net_value, 2),
            status=net_status,
            source="financial_formula_v1",
            note=None,
        )

    source_quality = {
        "orders": source_orders,
        "sales": source_sales,
        "realization": source_realization,
    }

    key_metrics = [
        orders_count,
        sales_count,
        returns_count,
        orders_amount,
        sales_amount,
        seller_payout,
        logistics_cost,
        storage_cost,
        deductions_amount,
        net_realization_amount,
    ]
    warnings.extend(normalized_bundle.warnings)

    if resolution.actual_date is None and _source_usable(source_realization):
        warnings.append("realization source is available but no usable date was resolved")

    financial_status = _overall_financial_status(key_metrics)
    warnings.append(f"financial_status={financial_status}")

    return FinancialMetricsSection(
        orders_count=orders_count,
        sales_count=sales_count,
        returns_count=returns_count,
        orders_amount=orders_amount,
        sales_amount=sales_amount,
        seller_payout=seller_payout,
        logistics_cost=logistics_cost,
        storage_cost=storage_cost,
        deductions_amount=deductions_amount,
        net_realization_amount=net_realization_amount,
        realization_target_date=resolution.target_date,
        realization_actual_date=resolution.actual_date,
        fallback_used=resolution.fallback_used,
        lag_days=resolution.lag_days,
        source_quality=source_quality,
        warnings=warnings,
    )
