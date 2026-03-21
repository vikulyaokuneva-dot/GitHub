"""Financial metrics assembler (expanded contour)."""

from __future__ import annotations

from typing import Any, Iterable

from ...core.contracts import FinancialMetricsSection, MetricStatus, MetricValue, NormalizedBundle, NormalizedSaleRecord
from ...warnings_utils import append_warning, dedupe_warnings, extend_warnings
from .components import classify_realization_components
from .lag_fallback import resolve_realization_window


USABLE_SOURCE_STATES = {"ok", "partial"}
CORE_EXACT_COST_KEYS = ("logistics_cost", "storage_cost", "deductions_amount")
ESTIMATED_PROXY_NOTE = "estimated/proxy: calculated without realization components"


def _metric(value: float | int | None, *, status: MetricStatus, source: str | None, note: str | None = None) -> MetricValue:
    return MetricValue(value=value, status=status.value, source=source, note=note)


def _unavailable_metric(*, source: str, note: str) -> MetricValue:
    return _metric(None, status=MetricStatus.UNAVAILABLE, source=source, note=note)


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
    return [record for record in records if getter(record) == target_date]


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


def _metric_from_count(*, count: int | None, source_state: str, source: str, forced_partial: bool = False, note: str | None = None) -> MetricValue:
    status = _base_status(source_state, forced_partial=forced_partial)
    if status == MetricStatus.UNAVAILABLE:
        return _metric(None, status=status, source=source, note=note)
    return _metric(int(count or 0), status=status, source=source, note=note)


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
    numeric = [float(value) for value in values if value is not None]
    has_missing = any(value is None for value in values)
    if not numeric:
        if allow_zero_if_no_rows and not has_missing:
            return _metric(0.0, status=status, source=source, note=None)
        return _metric(None, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)
    total = sum(numeric)
    if has_missing or status == MetricStatus.PARTIAL:
        return _metric(total, status=MetricStatus.PARTIAL, source=source, note=note_if_missing)
    return _metric(total, status=MetricStatus.CONFIRMED, source=source, note=None)


def _quality_to_status(value: str | None) -> MetricStatus:
    if value == MetricStatus.CONFIRMED.value:
        return MetricStatus.CONFIRMED
    if value == MetricStatus.PARTIAL.value:
        return MetricStatus.PARTIAL
    return MetricStatus.UNAVAILABLE


def _component_metric(*, value: float | None, quality: str | None, source: str, fallback_used: bool, note_if_unavailable: str) -> MetricValue:
    status = _quality_to_status(quality)
    if fallback_used and status == MetricStatus.CONFIRMED:
        status = MetricStatus.PARTIAL
    if status == MetricStatus.UNAVAILABLE:
        return _metric(None, status=status, source=source, note=note_if_unavailable)
    return _metric(value, status=status, source=source, note=(note_if_unavailable if value is None else None))


def _sanitize_note_for_present_value(metric: MetricValue, *, note_if_conflict: str | None = None) -> MetricValue:
    """Prevent contradictory wording like `value is present` + `unavailable` note."""

    if metric.value is None:
        return metric
    note = str(metric.note or "").strip().lower()
    if "unavailable" not in note:
        return metric
    return MetricValue(
        value=metric.value,
        status=metric.status,
        source=metric.source,
        note=note_if_conflict,
    )


def _metric_available(metric: MetricValue | None) -> bool:
    return bool(metric is not None and metric.value is not None and metric.status != MetricStatus.UNAVAILABLE.value)


def _collect_missing_dependencies(metrics: dict[str, MetricValue], required_keys: tuple[str, ...]) -> list[str]:
    return sorted([key for key in required_keys if not _metric_available(metrics.get(key))])


def calculate_exact_profitability(*, revenue_gross: MetricValue, cost_map: dict[str, MetricValue], fallback_used: bool) -> tuple[MetricValue, MetricValue, dict[str, Any]]:
    component_map = {"revenue_gross": revenue_gross, **cost_map}
    missing_required = _collect_missing_dependencies(component_map, ("revenue_gross", *CORE_EXACT_COST_KEYS))
    missing_optional = _collect_missing_dependencies(component_map, tuple(k for k in component_map if k not in {"revenue_gross", *CORE_EXACT_COST_KEYS}))
    if not _metric_available(revenue_gross):
        note = "exact profitability unavailable: missing dependencies ['revenue_gross']"
        metric = _unavailable_metric(source="financial_formula_exact_v1", note=note)
        return metric, metric, {
            "method": "realization_exact",
            "formula": "net_profit_like = revenue_gross - identifiable_costs",
            "dependencies": sorted(component_map.keys()),
            "missing_dependencies": sorted(set(missing_required + missing_optional + ["revenue_gross"])),
            "blockers": ["revenue_gross"],
            "confidence": "none",
        }

    # Exact model keeps maximum usable signal: if revenue is known, we subtract all
    # available realization cost components and mark the result as partial when
    # dependencies are incomplete.
    total_cost = sum(float(metric.value) for metric in cost_map.values() if metric.value is not None)
    gross_value = float(revenue_gross.value) - total_cost

    required_confirmed = all(
        _metric_available(component_map.get(key)) and component_map[key].status == MetricStatus.CONFIRMED.value
        for key in ("revenue_gross", *CORE_EXACT_COST_KEYS)
    )
    has_partial_inputs = any(
        metric.status != MetricStatus.CONFIRMED.value for metric in component_map.values() if metric.value is not None
    )

    status = MetricStatus.CONFIRMED
    if fallback_used or has_partial_inputs or missing_required:
        status = MetricStatus.PARTIAL
    if status == MetricStatus.CONFIRMED and not required_confirmed:
        status = MetricStatus.PARTIAL

    note_parts = ["profit-like metric without COGS/taxes/ads"]
    if missing_required:
        note_parts.append(f"incomplete exact dependencies: {missing_required}")
    elif missing_optional:
        note_parts.append(f"optional components unavailable: {missing_optional}")
    note = "; ".join(note_parts)
    metric = _metric(gross_value, status=status, source="financial_formula_exact_v1", note=note)
    return metric, metric, {
        "method": "realization_exact",
        "formula": "net_profit_like = revenue_gross - identifiable_costs",
        "dependencies": sorted(component_map.keys()),
        "missing_dependencies": sorted(set(missing_required + missing_optional)),
        "blockers": list(missing_required),
        "confidence": ("high" if status == MetricStatus.CONFIRMED else "medium"),
    }


def calculate_estimated_profitability(*, sales_amount: MetricValue, seller_payout: MetricValue) -> tuple[MetricValue, MetricValue, dict[str, Any]]:
    dependency_map = {"sales_amount": sales_amount, "seller_payout": seller_payout}
    missing = _collect_missing_dependencies(dependency_map, ("sales_amount", "seller_payout"))
    if missing:
        note = f"estimated/proxy profitability unavailable: missing dependencies {missing}"
        metric = _unavailable_metric(source="financial_formula_estimated_v1", note=note)
        return metric, metric, {
            "method": "seller_payout_proxy",
            "formula": "approx_net_profit_like = seller_payout; approx_margin_like = seller_payout / sales_amount",
            "dependencies": sorted(dependency_map.keys()),
            "missing_dependencies": missing,
            "blockers": missing,
            "confidence": "none",
            "warning": "estimated/proxy profitability unavailable: insufficient data",
        }
    confidence = "medium"
    if sales_amount.status != MetricStatus.CONFIRMED.value or seller_payout.status != MetricStatus.CONFIRMED.value:
        confidence = "low"
    metric = _metric(
        float(seller_payout.value),
        status=MetricStatus.PARTIAL,
        source="financial_formula_estimated_v1",
        note=ESTIMATED_PROXY_NOTE,
    )
    return metric, metric, {
        "method": "seller_payout_proxy",
        "formula": "approx_net_profit_like = seller_payout; approx_margin_like = seller_payout / sales_amount",
        "dependencies": sorted(dependency_map.keys()),
        "missing_dependencies": [],
        "blockers": [],
        "confidence": confidence,
        "warning": ESTIMATED_PROXY_NOTE,
    }


def calculate_margin(*, profit_metric: MetricValue, revenue_metric: MetricValue, method: str) -> MetricValue:
    if not _metric_available(profit_metric) or not _metric_available(revenue_metric):
        return _unavailable_metric(source="financial_formula_margin_v1", note="margin_like unavailable: missing profit or revenue")
    denominator = float(revenue_metric.value)
    if denominator <= 0:
        return _unavailable_metric(source="financial_formula_margin_v1", note="margin_like unavailable: revenue must be positive")
    status = MetricStatus.PARTIAL
    if profit_metric.status == MetricStatus.CONFIRMED.value and revenue_metric.status == MetricStatus.CONFIRMED.value:
        status = MetricStatus.CONFIRMED
    note = ESTIMATED_PROXY_NOTE if ("estimated" in method or "proxy" in method) else (profit_metric.note or None)
    return _metric(float(profit_metric.value) / denominator, status=status, source="financial_formula_margin_v1", note=note)


def resolve_financial_confidence(*, financial_model_mode: str, fallback_used: bool, selected_profit_metric: MetricValue, selected_margin_metric: MetricValue, estimate_confidence: str | None) -> str:
    if financial_model_mode == "unavailable":
        return "none"
    if financial_model_mode == "estimated":
        return str(estimate_confidence or "low")
    if selected_profit_metric.status == MetricStatus.CONFIRMED.value and selected_margin_metric.status == MetricStatus.CONFIRMED.value and not fallback_used:
        return "high"
    return "medium"


def _financial_component_lists(component_metrics: dict[str, MetricValue]) -> tuple[list[str], list[str]]:
    available = sorted([name for name, metric in component_metrics.items() if _metric_available(metric)])
    missing = sorted([name for name, metric in component_metrics.items() if not _metric_available(metric)])
    return available, missing


def _build_metric_provenance(*, metric: MetricValue, source_date: str | None, derivation_method: str, confidence: str, dependencies: list[str], missing_dependencies: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_name": metric.source,
        "source_date": source_date,
        "derivation_method": derivation_method,
        "confidence": confidence,
        "missing_dependencies": list(missing_dependencies),
    }
    if dependencies:
        payload["dependencies"] = list(dependencies)
    if metric.status == MetricStatus.PARTIAL.value:
        payload["partial_reason"] = metric.note or "partial evidence"
    return payload


def assemble_financial_metrics(normalized_bundle: NormalizedBundle) -> FinancialMetricsSection:
    target_date = _target_date(normalized_bundle)
    source_orders = _source_state(normalized_bundle, "orders")
    source_sales = _source_state(normalized_bundle, "sales")
    source_realization = _source_state(normalized_bundle, "realization")
    orders_for_day = _filter_by_date(normalized_bundle.orders, lambda row: row.order_date, target_date)
    sales_for_day = _filter_by_date(normalized_bundle.sales, lambda row: row.sale_date, target_date)
    return_rows = [row for row in sales_for_day if _is_return_sale(row) is True]
    sale_rows = [row for row in sales_for_day if _is_return_sale(row) is False]
    resolution = resolve_realization_window(normalized_bundle, normalized_bundle.run_context)
    realization_rows_for_actual_date = _filter_by_date(
        normalized_bundle.realization,
        lambda row: row.event_date,
        resolution.actual_date,
    )
    realization_detected_operations = sorted(
        {
            str(row.event_type).strip().lower()
            for row in realization_rows_for_actual_date
            if str(row.event_type or "").strip()
        }
    )
    realization_status_debug = normalized_bundle.source_statuses.get("realization")
    realization_status_debug = (
        dict(realization_status_debug.debug)
        if realization_status_debug is not None and isinstance(realization_status_debug.debug, dict)
        else {}
    )
    realization_extraction_mode = str(
        realization_status_debug.get("realization_extraction_mode")
        or realization_status_debug.get("extraction_mode")
        or "unknown"
    ).strip()
    if not realization_extraction_mode:
        realization_extraction_mode = "unknown"
    components = classify_realization_components(normalized_bundle, actual_date=resolution.actual_date)
    warnings: list[str] = []
    extend_warnings(warnings, resolution.warnings, namespace="realization")
    extend_warnings(warnings, components.warnings, namespace="realization")
    orders_count = _metric_from_count(count=len(orders_for_day), source_state=source_orders, source="orders")
    orders_amount = _metric_from_amount_values(values=[(float(row.price) * float(row.quantity or 1.0)) if row.price is not None else None for row in orders_for_day], source_state=source_orders, source="orders", allow_zero_if_no_rows=True, note_if_missing="orders amount is partially unavailable")
    if _source_usable(source_sales):
        sales_count = _metric_from_count(count=len(sale_rows), source_state=source_sales, source="sales")
        returns_count = _metric_from_count(count=len(return_rows), source_state=source_sales, source="sales")
        sales_amount = _metric_from_amount_values(values=[row.sale_amount for row in sale_rows], source_state=source_sales, source="sales", allow_zero_if_no_rows=True, note_if_missing="sales amount is partially unavailable")
    else:
        sales_count = _metric_from_count(count=(0 if components.sales_amount is not None else None), source_state=source_realization, source="realization", forced_partial=True, note="derived from realization components")
        returns_count = _metric_from_count(count=None, source_state=source_realization, source="realization", forced_partial=True, note="returns count unavailable without sales source")
        sales_amount = _component_metric(value=components.sales_amount, quality=components.component_quality.get("revenue"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="sales amount derived from realization is unavailable")
        append_warning(warnings, "sales source unavailable: using realization components", namespace="financial")
    seller_payout = _component_metric(value=components.seller_payout, quality=components.component_quality.get("payout"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="seller payout is unavailable in realization components")
    if seller_payout.value is None and _source_usable(source_sales):
        seller_payout = _metric_from_amount_values(values=[row.payout_amount for row in sale_rows], source_state=source_sales, source="sales", forced_partial=True, note_if_missing="seller payout is derived from sales source as an estimate/proxy")
    seller_payout = _sanitize_note_for_present_value(
        seller_payout,
        note_if_conflict="seller payout is derived from partially available payout rows",
    )
    revenue_gross = _metric(float(sales_amount.value), status=MetricStatus.PARTIAL if sales_amount.status == MetricStatus.PARTIAL.value else MetricStatus.CONFIRMED, source="sales", note="revenue_gross derived from sales amount") if (sales_amount.value is not None and _source_usable(source_sales)) else _component_metric(value=components.revenue_gross, quality=components.component_quality.get("revenue"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="revenue gross is unavailable")
    logistics_cost = _component_metric(value=components.logistics_cost, quality=components.component_quality.get("logistics"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="logistics cost is unavailable")
    storage_cost = _component_metric(value=components.storage_cost, quality=components.component_quality.get("storage"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="storage cost is unavailable")
    deductions_amount = _component_metric(value=components.deductions_amount, quality=components.component_quality.get("deductions"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="deductions amount is unavailable")
    commission_amount = _component_metric(value=components.commission_amount, quality=components.component_quality.get("commission"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="commission amount is unavailable")
    acquiring_amount = _component_metric(value=components.acquiring_amount, quality=components.component_quality.get("acquiring"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="acquiring amount is unavailable")
    pvz_amount = _component_metric(value=components.pvz_amount, quality=components.component_quality.get("pvz"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="PVZ amount is unavailable")
    penalties_amount = _component_metric(value=components.penalties_amount, quality=components.component_quality.get("penalties"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="penalties amount is unavailable")
    acceptance_amount = _component_metric(value=components.acceptance_amount, quality=components.component_quality.get("acceptance"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="acceptance amount is unavailable")
    paid_acceptance_amount = _component_metric(value=components.paid_acceptance_amount, quality=components.component_quality.get("paid_acceptance"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="paid acceptance amount is unavailable")
    other_costs_amount = _component_metric(value=components.other_costs_amount, quality=components.component_quality.get("other_costs"), source="realization_components", fallback_used=bool(resolution.fallback_used), note_if_unavailable="other costs amount is unavailable")
    if any(component.status == MetricStatus.UNAVAILABLE.value for component in [sales_amount, logistics_cost, storage_cost, deductions_amount]):
        net_realization_amount = _unavailable_metric(source="financial_formula_net_realization_v2", note="insufficient required components for net realization")
    else:
        net_value = float(sales_amount.value or 0.0) - sum(float(component.value or 0.0) for component in [logistics_cost, storage_cost, deductions_amount, acceptance_amount, paid_acceptance_amount])
        net_status = MetricStatus.CONFIRMED if all(component.status == MetricStatus.CONFIRMED.value for component in [sales_amount, logistics_cost, storage_cost, deductions_amount, acceptance_amount, paid_acceptance_amount]) else MetricStatus.PARTIAL
        net_realization_amount = _metric(net_value, status=net_status, source="financial_formula_net_realization_v2", note=("optional acceptance components are unavailable" if any(component.value is None for component in [acceptance_amount, paid_acceptance_amount]) else None))
    cost_map = {"commission_amount": commission_amount, "acquiring_amount": acquiring_amount, "logistics_cost": logistics_cost, "storage_cost": storage_cost, "deductions_amount": deductions_amount, "pvz_amount": pvz_amount, "penalties_amount": penalties_amount, "acceptance_amount": acceptance_amount, "paid_acceptance_amount": paid_acceptance_amount, "other_costs_amount": other_costs_amount}
    exact_gross, exact_net, exact_meta = calculate_exact_profitability(revenue_gross=revenue_gross, cost_map=cost_map, fallback_used=bool(resolution.fallback_used))
    estimated_gross, estimated_net, estimate_meta = calculate_estimated_profitability(sales_amount=sales_amount, seller_payout=seller_payout)
    realization_available = bool(_source_usable(source_realization) and resolution.actual_date)
    financial_model_mode = "exact" if (realization_available and exact_net.status != MetricStatus.UNAVAILABLE.value) else ("estimated" if estimated_net.status != MetricStatus.UNAVAILABLE.value else "unavailable")
    if financial_model_mode == "exact":
        gross_profit_like, net_profit_like, profile = exact_gross, exact_net, exact_meta
        estimate_used, estimate_method, estimate_formula, estimate_dependencies, estimate_warning = False, None, None, [], None
    elif financial_model_mode == "estimated":
        gross_profit_like, net_profit_like, profile = estimated_gross, estimated_net, estimate_meta
        estimate_used = True
        estimate_method = str(estimate_meta.get("method", "")) or None
        estimate_formula = str(estimate_meta.get("formula", "")) or None
        estimate_dependencies = [str(v) for v in estimate_meta.get("dependencies", [])]
        estimate_warning = str(estimate_meta.get("warning", "")) or None
        append_warning(warnings, ESTIMATED_PROXY_NOTE, namespace="financial")
    else:
        gross_profit_like = _unavailable_metric(source="financial_formula_v3", note="insufficient evidence for profitability calculation")
        net_profit_like = _unavailable_metric(source="financial_formula_v3", note="insufficient evidence for profitability calculation")
        profile = {
            "method": "unavailable",
            "formula": "",
            "dependencies": [],
            "missing_dependencies": sorted(set([*exact_meta.get("missing_dependencies", []), *estimate_meta.get("missing_dependencies", [])])),
            "blockers": sorted(set([*exact_meta.get("blockers", []), *estimate_meta.get("blockers", [])])),
            "confidence": "none",
        }
        estimate_used = False
        estimate_method = str(estimate_meta.get("method", "")) or None
        estimate_formula = str(estimate_meta.get("formula", "")) or None
        estimate_dependencies = [str(v) for v in estimate_meta.get("dependencies", [])]
        estimate_warning = str(estimate_meta.get("warning", "")) or None
    margin = calculate_margin(profit_metric=net_profit_like, revenue_metric=(sales_amount if financial_model_mode == "estimated" else revenue_gross), method=("estimated_proxy" if financial_model_mode == "estimated" else "realization_exact"))
    financial_confidence = resolve_financial_confidence(financial_model_mode=financial_model_mode, fallback_used=bool(resolution.fallback_used), selected_profit_metric=net_profit_like, selected_margin_metric=margin, estimate_confidence=str(estimate_meta.get("confidence", "none")))
    component_quality = {
        **dict(components.component_quality),
        "revenue": revenue_gross.status, "payout": seller_payout.status, "commission": commission_amount.status, "acquiring": acquiring_amount.status,
        "logistics": logistics_cost.status, "storage": storage_cost.status, "deductions": deductions_amount.status, "pvz": pvz_amount.status,
        "penalties": penalties_amount.status, "acceptance": acceptance_amount.status, "paid_acceptance": paid_acceptance_amount.status,
        "other_costs": other_costs_amount.status, "gross_profit_like": gross_profit_like.status, "net_profit_like": net_profit_like.status, "margin": margin.status,
    }
    tracked_components = {"sales_amount": sales_amount, "seller_payout": seller_payout, "revenue_gross": revenue_gross, "commission_amount": commission_amount, "acquiring_amount": acquiring_amount, "logistics_cost": logistics_cost, "storage_cost": storage_cost, "deductions_amount": deductions_amount, "pvz_amount": pvz_amount, "penalties_amount": penalties_amount, "acceptance_amount": acceptance_amount, "paid_acceptance_amount": paid_acceptance_amount, "other_costs_amount": other_costs_amount, "net_profit_like": net_profit_like, "margin": margin}
    financial_available_components, financial_missing_components = _financial_component_lists(tracked_components)
    metric_provenance = {
        "gross_profit_like": _build_metric_provenance(metric=gross_profit_like, source_date=resolution.actual_date, derivation_method=str(profile.get("method", "unknown")), confidence=financial_confidence, dependencies=[str(v) for v in profile.get("dependencies", [])], missing_dependencies=[str(v) for v in profile.get("missing_dependencies", [])]),
        "net_profit_like": _build_metric_provenance(metric=net_profit_like, source_date=resolution.actual_date, derivation_method=str(profile.get("method", "unknown")), confidence=financial_confidence, dependencies=[str(v) for v in profile.get("dependencies", [])], missing_dependencies=[str(v) for v in profile.get("missing_dependencies", [])]),
        "margin": _build_metric_provenance(metric=margin, source_date=resolution.actual_date, derivation_method=("estimated_proxy" if financial_model_mode == "estimated" else "realization_exact"), confidence=financial_confidence, dependencies=(["net_profit_like", "sales_amount"] if financial_model_mode == "estimated" else ["net_profit_like", "revenue_gross"]), missing_dependencies=([] if margin.status != MetricStatus.UNAVAILABLE.value else ["net_profit_like", "revenue_base"])),
    }
    financial_mode_compat = "full" if financial_model_mode == "exact" else "partial" if financial_model_mode == "estimated" else "unavailable"
    extend_warnings(warnings, normalized_bundle.warnings)
    warnings = dedupe_warnings(warnings)
    return FinancialMetricsSection(
        orders_count=orders_count, sales_count=sales_count, returns_count=returns_count, orders_amount=orders_amount, sales_amount=sales_amount, seller_payout=seller_payout,
        logistics_cost=logistics_cost, storage_cost=storage_cost, deductions_amount=deductions_amount, net_realization_amount=net_realization_amount,
        revenue_gross=revenue_gross, commission_amount=commission_amount, acquiring_amount=acquiring_amount, pvz_amount=pvz_amount, penalties_amount=penalties_amount,
        acceptance_amount=acceptance_amount, paid_acceptance_amount=paid_acceptance_amount, other_costs_amount=other_costs_amount, gross_profit_like=gross_profit_like,
        net_profit_like=net_profit_like, margin=margin, profit_formula_note=(str(profile.get("formula", "")) or None), realization_target_date=resolution.target_date,
        realization_actual_date=resolution.actual_date, fallback_used=resolution.fallback_used, lag_days=resolution.lag_days, financial_model_mode=financial_model_mode,
        financial_confidence=financial_confidence, financial_source_date=resolution.actual_date, realization_rows_count=len(realization_rows_for_actual_date),
        realization_extraction_mode=realization_extraction_mode, realization_detected_operations=realization_detected_operations, financial_mode=financial_mode_compat,
        financial_missing_components=financial_missing_components, financial_available_components=financial_available_components, profitability_estimate_used=estimate_used,
        profitability_estimate_method=estimate_method, profitability_estimate_formula=estimate_formula, profitability_estimate_dependencies=estimate_dependencies,
        profitability_estimate_warning=estimate_warning, profitability_method=str(profile.get("method", "unavailable")),
        profitability_dependencies=[str(v) for v in profile.get("dependencies", [])], profitability_blockers=[str(v) for v in profile.get("blockers", [])], metric_provenance=metric_provenance,
        source_quality={"orders": source_orders, "sales": source_sales, "realization": source_realization}, component_quality=component_quality, warnings=warnings,
    )
