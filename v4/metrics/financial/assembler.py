"""Financial metrics assembler (expanded contour).

Input: NormalizedBundle.
Output: FinancialMetricsSection.
Does not compute facts/decisions and does not render outputs.
"""

from __future__ import annotations

from typing import Iterable

from ...core.contracts import (
    FinancialMetricsSection,
    MetricStatus,
    MetricValue,
    NormalizedBundle,
    NormalizedSaleRecord,
)
from ...warnings_utils import append_warning, dedupe_warnings, extend_warnings
from .components import classify_realization_components
from .lag_fallback import resolve_realization_window


USABLE_SOURCE_STATES = {"ok", "partial"}


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


def _sum_amounts(values: list[float | None]) -> tuple[float | None, bool]:
    numeric = [float(value) for value in values if value is not None]
    has_missing = any(value is None for value in values)
    if not numeric:
        return None, has_missing
    return round(sum(numeric), 2), has_missing


def _metric_from_amount_values(
    *,
    values: list[float | None],
    source_state: str,
    source: str,
    forced_partial: bool = False,
    allow_zero_if_no_rows: bool = False,
    note_if_missing: str | None = None,
) -> MetricValue:
    status = _base_status(source_state, forced_partial=forced_partial)
    if status == MetricStatus.UNAVAILABLE:
        return _metric(None, status=status, source=source, note=note_if_missing)

    if not values:
        if allow_zero_if_no_rows:
            return _metric(0.0, status=status, source=source, note=None)
        return _metric(None, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)

    total, has_missing = _sum_amounts(values)
    if total is None:
        if allow_zero_if_no_rows and not has_missing:
            return _metric(0.0, status=status, source=source, note=None)
        return _metric(None, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)

    if has_missing or status == MetricStatus.PARTIAL:
        return _metric(total, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)
    return _metric(total, status=MetricStatus.CONFIRMED, source=source, note=None)


def _quality_to_status(value: str | None) -> MetricStatus:
    if value == MetricStatus.CONFIRMED.value:
        return MetricStatus.CONFIRMED
    if value == MetricStatus.PARTIAL.value:
        return MetricStatus.PARTIAL
    return MetricStatus.UNAVAILABLE


def _component_metric(
    *,
    value: float | None,
    quality: str | None,
    source: str,
    fallback_used: bool,
    note_if_unavailable: str,
) -> MetricValue:
    status = _quality_to_status(quality)
    if fallback_used and status == MetricStatus.CONFIRMED:
        status = MetricStatus.PARTIAL

    if status == MetricStatus.UNAVAILABLE:
        return _metric(None, status=status, source=source, note=note_if_unavailable)

    return _metric(value, status=status, source=source, note=(note_if_unavailable if value is None else None))


def _overall_financial_status(metrics: list[MetricValue]) -> str:
    states = {metric.status for metric in metrics}
    if not states:
        return MetricStatus.UNAVAILABLE.value
    if states == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in states or MetricStatus.PARTIAL.value in states:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def _build_profit_like(
    *,
    revenue_gross: MetricValue,
    seller_payout: MetricValue,
    commission_amount: MetricValue,
    acquiring_amount: MetricValue,
    logistics_cost: MetricValue,
    storage_cost: MetricValue,
    pvz_amount: MetricValue,
    penalties_amount: MetricValue,
    other_costs_amount: MetricValue,
    deductions_amount: MetricValue,
    fallback_used: bool,
) -> tuple[MetricValue, MetricValue, str | None]:
    cost_components_full = [
        commission_amount,
        acquiring_amount,
        logistics_cost,
        storage_cost,
        pvz_amount,
        penalties_amount,
        other_costs_amount,
        deductions_amount,
    ]

    formula_note: str | None = None
    gross_profit_like: MetricValue

    if (
        revenue_gross.value is not None
        and all(component.value is not None for component in cost_components_full)
        and all(component.status != MetricStatus.UNAVAILABLE.value for component in cost_components_full)
        and revenue_gross.status != MetricStatus.UNAVAILABLE.value
    ):
        gross_value = float(revenue_gross.value) - sum(float(component.value) for component in cost_components_full)
        gross_status = MetricStatus.CONFIRMED
        if fallback_used or revenue_gross.status != MetricStatus.CONFIRMED.value or any(
            component.status != MetricStatus.CONFIRMED.value for component in cost_components_full
        ):
            gross_status = MetricStatus.PARTIAL
        formula_note = (
            "gross_profit_like = revenue_gross - commission - acquiring - logistics - storage "
            "- pvz - penalties - other_costs - deductions"
        )
        gross_profit_like = _metric(
            round(gross_value, 2),
            status=gross_status,
            source="financial_formula_gross_v2",
            note="profit-like metric without COGS/taxes",
        )
    else:
        payout_cost_components = [
            logistics_cost,
            storage_cost,
            pvz_amount,
            penalties_amount,
            other_costs_amount,
            deductions_amount,
        ]
        if (
            seller_payout.value is not None
            and all(component.value is not None for component in payout_cost_components)
            and all(component.status != MetricStatus.UNAVAILABLE.value for component in payout_cost_components)
            and seller_payout.status != MetricStatus.UNAVAILABLE.value
        ):
            gross_value = float(seller_payout.value) - sum(float(component.value) for component in payout_cost_components)
            formula_note = (
                "gross_profit_like = seller_payout - logistics - storage - pvz - penalties "
                "- other_costs - deductions"
            )
            gross_profit_like = _metric(
                round(gross_value, 2),
                status=MetricStatus.PARTIAL,
                source="financial_formula_payout_v2",
                note="fallback profit-like metric derived from payout basis",
            )
        else:
            formula_note = "gross_profit_like is unavailable: insufficient reliable components"
            gross_profit_like = _metric(
                None,
                status=MetricStatus.UNAVAILABLE,
                source="financial_formula_v2",
                note="insufficient reliable components",
            )

    if gross_profit_like.value is None:
        net_profit_like = _metric(
            None,
            status=_quality_to_status(gross_profit_like.status),
            source="financial_formula_net_v2",
            note="net_profit_like unavailable because gross_profit_like is unavailable",
        )
    else:
        net_profit_like = _metric(
            gross_profit_like.value,
            status=MetricStatus.PARTIAL,
            source="financial_formula_net_v2",
            note="profit-like metric; COGS/taxes/ads are not included",
        )

    return gross_profit_like, net_profit_like, formula_note


def assemble_financial_metrics(normalized_bundle: NormalizedBundle) -> FinancialMetricsSection:
    """Assemble expanded and explainable financial contour.

    Counting rule on this stage:
    - orders_count, sales_count, returns_count are record-based counts,
      not quantity sums.
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
    components = classify_realization_components(normalized_bundle, actual_date=resolution.actual_date)

    warnings = list(resolution.warnings)
    warnings.extend(components.warnings)

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

    orders_amount = _metric_from_amount_values(
        values=orders_amount_values,
        source_state=source_orders,
        source="orders",
        allow_zero_if_no_rows=True,
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
        sales_amount = _metric_from_amount_values(
            values=[row.sale_amount for row in sale_rows],
            source_state=source_sales,
            source="sales",
            allow_zero_if_no_rows=True,
            note_if_missing="sales amount is partially unavailable",
        )
    else:
        sales_count = _metric_from_count(
            count=(0 if components.sales_amount is not None else None),
            source_state=source_realization,
            source="realization",
            forced_partial=True,
            note="derived from realization components",
        )
        returns_count = _metric_from_count(
            count=None,
            source_state=source_realization,
            source="realization",
            forced_partial=True,
            note="returns count unavailable without sales source",
        )
        sales_amount = _component_metric(
            value=components.sales_amount,
            quality=components.component_quality.get("revenue"),
            source="realization_components",
            fallback_used=bool(resolution.fallback_used),
            note_if_unavailable="sales amount derived from realization is unavailable",
        )
        warnings.append("sales source unavailable: using realization components")

    seller_payout = _component_metric(
        value=components.seller_payout,
        quality=components.component_quality.get("payout"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="seller payout is unavailable in realization components",
    )

    if seller_payout.value is None and _source_usable(source_sales):
        seller_payout = _metric_from_amount_values(
            values=[row.payout_amount for row in sale_rows],
            source_state=source_sales,
            source="sales",
            forced_partial=True,
            allow_zero_if_no_rows=False,
            note_if_missing="seller payout is unavailable",
        )

    if sales_amount.value is not None and _source_usable(source_sales):
        revenue_gross = _metric(
            float(sales_amount.value),
            status=MetricStatus.PARTIAL if sales_amount.status == MetricStatus.PARTIAL.value else MetricStatus.CONFIRMED,
            source="sales",
            note="revenue_gross derived from sales amount",
        )
    else:
        revenue_gross = _component_metric(
            value=components.revenue_gross,
            quality=components.component_quality.get("revenue"),
            source="realization_components",
            fallback_used=bool(resolution.fallback_used),
            note_if_unavailable="revenue gross is unavailable",
        )

    logistics_cost = _component_metric(
        value=components.logistics_cost,
        quality=components.component_quality.get("logistics"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="logistics cost is unavailable",
    )
    storage_cost = _component_metric(
        value=components.storage_cost,
        quality=components.component_quality.get("storage"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="storage cost is unavailable",
    )
    deductions_amount = _component_metric(
        value=components.deductions_amount,
        quality=components.component_quality.get("deductions"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="deductions amount is unavailable",
    )
    commission_amount = _component_metric(
        value=components.commission_amount,
        quality=components.component_quality.get("commission"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="commission amount is unavailable",
    )
    acquiring_amount = _component_metric(
        value=components.acquiring_amount,
        quality=components.component_quality.get("acquiring"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="acquiring amount is unavailable",
    )
    pvz_amount = _component_metric(
        value=components.pvz_amount,
        quality=components.component_quality.get("pvz"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="PVZ amount is unavailable",
    )
    penalties_amount = _component_metric(
        value=components.penalties_amount,
        quality=components.component_quality.get("penalties"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="penalties amount is unavailable",
    )
    other_costs_amount = _component_metric(
        value=components.other_costs_amount,
        quality=components.component_quality.get("other_costs"),
        source="realization_components",
        fallback_used=bool(resolution.fallback_used),
        note_if_unavailable="other costs amount is unavailable",
    )

    net_components = [sales_amount, logistics_cost, storage_cost, deductions_amount]
    if any(component.status == MetricStatus.UNAVAILABLE.value for component in net_components):
        net_realization_amount = _metric(
            None,
            status=MetricStatus.UNAVAILABLE,
            source="financial_formula_net_realization_v1",
            note="insufficient components for net realization",
        )
    elif any(component.value is None for component in net_components):
        net_realization_amount = _metric(
            None,
            status=MetricStatus.PARTIAL,
            source="financial_formula_net_realization_v1",
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
        if any(component.status != MetricStatus.CONFIRMED.value for component in net_components):
            net_status = MetricStatus.PARTIAL
        net_realization_amount = _metric(
            round(net_value, 2),
            status=net_status,
            source="financial_formula_net_realization_v1",
            note=None,
        )

    gross_profit_like, net_profit_like, profit_formula_note = _build_profit_like(
        revenue_gross=revenue_gross,
        seller_payout=seller_payout,
        commission_amount=commission_amount,
        acquiring_amount=acquiring_amount,
        logistics_cost=logistics_cost,
        storage_cost=storage_cost,
        pvz_amount=pvz_amount,
        penalties_amount=penalties_amount,
        other_costs_amount=other_costs_amount,
        deductions_amount=deductions_amount,
        fallback_used=bool(resolution.fallback_used),
    )

    source_quality = {
        "orders": source_orders,
        "sales": source_sales,
        "realization": source_realization,
    }

    component_quality = dict(components.component_quality)
    component_quality.update(
        {
            "revenue": revenue_gross.status,
            "payout": seller_payout.status,
            "commission": commission_amount.status,
            "acquiring": acquiring_amount.status,
            "logistics": logistics_cost.status,
            "storage": storage_cost.status,
            "deductions": deductions_amount.status,
            "pvz": pvz_amount.status,
            "penalties": penalties_amount.status,
            "other_costs": other_costs_amount.status,
        }
    )

    extend_warnings(warnings, normalized_bundle.warnings)

    key_metrics = [
        orders_count,
        sales_count,
        returns_count,
        orders_amount,
        sales_amount,
        seller_payout,
        revenue_gross,
        commission_amount,
        acquiring_amount,
        logistics_cost,
        storage_cost,
        deductions_amount,
        pvz_amount,
        penalties_amount,
        other_costs_amount,
        net_realization_amount,
        gross_profit_like,
        net_profit_like,
    ]

    financial_status = _overall_financial_status(key_metrics)
    append_warning(warnings, f"financial_status={financial_status}")
    warnings = dedupe_warnings(warnings)

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
        revenue_gross=revenue_gross,
        commission_amount=commission_amount,
        acquiring_amount=acquiring_amount,
        pvz_amount=pvz_amount,
        penalties_amount=penalties_amount,
        other_costs_amount=other_costs_amount,
        gross_profit_like=gross_profit_like,
        net_profit_like=net_profit_like,
        profit_formula_note=profit_formula_note,
        realization_target_date=resolution.target_date,
        realization_actual_date=resolution.actual_date,
        fallback_used=resolution.fallback_used,
        lag_days=resolution.lag_days,
        source_quality=source_quality,
        component_quality=component_quality,
        warnings=warnings,
    )
