"""Health metrics assembler.

Input: NormalizedBundle and already assembled metrics sections.
Output: HealthMetricsSection with explainable score breakdown.
Does not recompute business KPI outside metrics stage.
"""

from __future__ import annotations

from typing import Any

from ..core.contracts import (
    AdsMetricsSection,
    FinancialMetricsSection,
    FunnelMetricsSection,
    HealthMetricsSection,
    MetricStatus,
    MetricValue,
    NormalizedBundle,
    StockMetricsSection,
)
from ..warnings_utils import append_warning, dedupe_warnings


USABLE_SOURCE_STATES = {"ok", "partial"}

HEALTH_POLICY_V1: dict[str, Any] = {
    "version": "health_policy_v1",
    "component_max_scores": {
        "profitability": 30.0,
        "ads": 20.0,
        "funnel": 20.0,
        "stock": 20.0,
        "data_quality": 10.0,
    },
    "profitability_thresholds": {
        "negative": 0.0,
        "low": 50.0,
        "medium": 200.0,
    },
    "ads_thresholds": {
        "roas_bad": 1.0,
        "roas_mid": 2.0,
        "conversion_bad": 0.01,
        "conversion_low": 0.02,
        "conversion_good": 0.03,
    },
    "funnel_thresholds": {
        "buy_rate_bad": 0.15,
        "buy_rate_mid": 0.30,
        "buy_rate_good": 0.50,
        "buy_from_impressions_good": 0.03,
    },
    "stock_thresholds": {
        "out_of_stock_ratio_bad": 0.50,
        "out_of_stock_ratio_mid": 0.20,
        "overstock_days_cover": 45.0,
    },
    "score_missing_component_penalty": 0.08,
}


def _metric(
    value: float | int | None,
    *,
    status: MetricStatus,
    source: str | None,
    note: str | None = None,
) -> MetricValue:
    return MetricValue(value=value, status=status.value, source=source, note=note)


def _to_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


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


def _status_from_metric_values(values: list[MetricValue]) -> MetricStatus:
    statuses = {str(value.status) for value in values if isinstance(value, MetricValue)}
    if not statuses:
        return MetricStatus.UNAVAILABLE
    if statuses == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED
    if MetricStatus.CONFIRMED.value in statuses or MetricStatus.PARTIAL.value in statuses:
        return MetricStatus.PARTIAL
    return MetricStatus.UNAVAILABLE


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _profitability_component(financial: FinancialMetricsSection | None) -> MetricValue:
    if financial is None:
        return _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="financial section is missing")

    metric = financial.net_profit_like
    metric_key = "net_profit_like"
    if metric.value is None and str(metric.status) == MetricStatus.UNAVAILABLE.value:
        metric = financial.gross_profit_like
        metric_key = "gross_profit_like"

    profit_value = _to_float(metric.value)
    if profit_value is None:
        status = MetricStatus.PARTIAL if str(metric.status) == MetricStatus.PARTIAL.value else MetricStatus.UNAVAILABLE
        return _metric(
            None,
            status=status,
            source=metric.source or "health_policy_v1",
            note=f"{metric_key} is unavailable for profitability component",
        )

    thresholds = HEALTH_POLICY_V1["profitability_thresholds"]
    if profit_value < thresholds["negative"]:
        score = 0.0
    elif profit_value <= thresholds["low"]:
        score = 10.0
    elif profit_value <= thresholds["medium"]:
        score = 20.0
    else:
        score = 30.0

    status = MetricStatus.CONFIRMED if str(metric.status) == MetricStatus.CONFIRMED.value else MetricStatus.PARTIAL
    return _metric(
        round(score, 2),
        status=status,
        source=metric.source or "health_policy_v1",
        note=f"profitability component from {metric_key}",
    )


def _ads_component(ads: AdsMetricsSection | None) -> MetricValue:
    if ads is None:
        return _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="ads section is missing")

    spend = _to_float(ads.spend.value)
    revenue = _to_float(ads.revenue.value)
    conversion = _to_float(ads.conversion_click_to_order.value)

    if spend is None and revenue is None and conversion is None:
        status = _status_from_metric_values([ads.spend, ads.revenue, ads.conversion_click_to_order])
        if status != MetricStatus.UNAVAILABLE:
            status = MetricStatus.PARTIAL
        return _metric(None, status=status, source="ads", note="ads evidence is insufficient")

    thresholds = HEALTH_POLICY_V1["ads_thresholds"]
    score = 10.0
    note = "ads component from spend/revenue/conversion"

    if spend is not None and spend <= 0:
        score = 12.0
        note = "ads spend is zero or negative; neutral ads component"
    elif spend is not None and spend > 0:
        if revenue is not None:
            roas = revenue / spend
            if roas < thresholds["roas_bad"]:
                score = 4.0
            elif roas < thresholds["roas_mid"]:
                score = 10.0
            else:
                score = 16.0
            note = f"ads component from ROAS={round(roas, 4)}"
        else:
            score = 10.0
            note = "ads revenue unavailable; ads component uses neutral base"

    if conversion is not None:
        if conversion < thresholds["conversion_bad"]:
            score -= 4.0
        elif conversion < thresholds["conversion_low"]:
            score -= 2.0
        elif conversion >= thresholds["conversion_good"]:
            score += 2.0

    score = _clamp(score, 0.0, 20.0)
    status = _status_from_metric_values([ads.spend, ads.revenue, ads.conversion_click_to_order])
    if status == MetricStatus.UNAVAILABLE:
        status = MetricStatus.PARTIAL

    return _metric(round(score, 2), status=status, source="ads", note=note)


def _funnel_component(funnel: FunnelMetricsSection | None) -> MetricValue:
    if funnel is None:
        return _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="funnel section is missing")

    primary_rate = _to_float(funnel.cr_buys_from_orders.value)
    fallback_orders = _to_float(funnel.orders.value)
    fallback_buys = _to_float(funnel.buys.value)

    rate = primary_rate
    rate_note = "funnel component from cr_buys_from_orders"
    rate_metrics = [funnel.cr_buys_from_orders, funnel.cr_buys_from_impressions]

    if rate is None:
        if fallback_orders is not None and fallback_buys is not None and fallback_orders > 0:
            rate = fallback_buys / fallback_orders
            rate_note = "funnel component from buys/orders fallback"
            rate_metrics = [funnel.orders, funnel.buys, funnel.cr_buys_from_impressions]
        else:
            status = _status_from_metric_values([funnel.cr_buys_from_orders, funnel.orders, funnel.buys])
            if status != MetricStatus.UNAVAILABLE:
                status = MetricStatus.PARTIAL
            return _metric(None, status=status, source="funnel", note="funnel conversion evidence is insufficient")

    thresholds = HEALTH_POLICY_V1["funnel_thresholds"]
    if rate < thresholds["buy_rate_bad"]:
        score = 4.0
    elif rate < thresholds["buy_rate_mid"]:
        score = 10.0
    elif rate < thresholds["buy_rate_good"]:
        score = 14.0
    else:
        score = 18.0

    from_impressions = _to_float(funnel.cr_buys_from_impressions.value)
    if from_impressions is not None and from_impressions >= thresholds["buy_from_impressions_good"]:
        score += 2.0

    score = _clamp(score, 0.0, 20.0)
    status = _status_from_metric_values(rate_metrics)
    if status == MetricStatus.UNAVAILABLE:
        status = MetricStatus.PARTIAL

    return _metric(round(score, 2), status=status, source="funnel", note=f"{rate_note}: rate={round(rate, 4)}")


def _stock_component(stock: StockMetricsSection | None) -> MetricValue:
    if stock is None:
        return _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="stock section is missing")

    out_of_stock = _to_float(stock.out_of_stock_items_count.value)
    in_stock = _to_float(stock.in_stock_items_count.value)

    if out_of_stock is None and in_stock is None:
        status = _status_from_metric_values([stock.out_of_stock_items_count, stock.in_stock_items_count])
        if status != MetricStatus.UNAVAILABLE:
            status = MetricStatus.PARTIAL
        return _metric(None, status=status, source="stock", note="stock availability evidence is insufficient")

    ratio: float | None = None
    denominator = 0.0
    if out_of_stock is not None and in_stock is not None:
        denominator = out_of_stock + in_stock
        if denominator > 0:
            ratio = out_of_stock / denominator

    if ratio is None:
        score = 10.0
        note = "stock component uses neutral base due to incomplete in/out stock denominator"
    else:
        thresholds = HEALTH_POLICY_V1["stock_thresholds"]
        if ratio >= thresholds["out_of_stock_ratio_bad"]:
            score = 4.0
        elif ratio >= thresholds["out_of_stock_ratio_mid"]:
            score = 10.0
        elif ratio >= 0.05:
            score = 14.0
        else:
            score = 18.0
        note = f"stock component from out_of_stock_ratio={round(ratio, 4)}"

    status = _status_from_metric_values([stock.out_of_stock_items_count, stock.in_stock_items_count])
    if status == MetricStatus.UNAVAILABLE:
        status = MetricStatus.PARTIAL

    return _metric(round(score, 2), status=status, source="stock", note=note)


def _data_quality_component(components: dict[str, MetricValue]) -> MetricValue:
    metrics = list(components.values())
    if not metrics:
        return _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="no health components")

    unavailable_count = sum(1 for metric in metrics if str(metric.status) == MetricStatus.UNAVAILABLE.value)
    partial_count = sum(1 for metric in metrics if str(metric.status) == MetricStatus.PARTIAL.value)
    available_count = sum(1 for metric in metrics if metric.value is not None)

    if available_count == 0:
        return _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="all components unavailable")

    score = 10.0 - (3.0 * partial_count) - (5.0 * unavailable_count)
    score = _clamp(score, 0.0, 10.0)
    status = MetricStatus.CONFIRMED if unavailable_count == 0 and partial_count == 0 else MetricStatus.PARTIAL

    return _metric(
        round(score, 2),
        status=status,
        source="health_policy_v1",
        note=f"data quality penalty from partial={partial_count}, unavailable={unavailable_count}",
    )


def _collect_stock_entities(normalized_bundle: NormalizedBundle) -> tuple[dict[str, float], int, int]:
    entities: dict[str, float] = {}
    unknown_with_stock = 0
    rows_with_quantity = 0

    for row in normalized_bundle.stocks:
        quantity = _to_float(row.quantity)
        if quantity is None or quantity <= 0:
            continue
        rows_with_quantity += 1
        entity = str(row.nm_id).strip() if row.nm_id not in (None, "") else ""
        if not entity:
            unknown_with_stock += 1
            continue
        entities[entity] = entities.get(entity, 0.0) + quantity

    return entities, unknown_with_stock, rows_with_quantity


def _collect_funnel_movement(normalized_bundle: NormalizedBundle) -> dict[str, float]:
    movement: dict[str, float] = {}
    for row in normalized_bundle.funnel:
        entity = str(row.entity_id).strip() if row.entity_id not in (None, "") else ""
        if not entity:
            continue
        orders = _to_float(row.orders)
        buys = _to_float(row.buys)
        if orders is None and buys is None:
            continue
        movement_value = (orders or 0.0) + (buys or 0.0)
        movement[entity] = movement.get(entity, 0.0) + movement_value
    return movement


def _dead_stock_metric(
    *,
    normalized_bundle: NormalizedBundle,
    stock_source_state: str,
    funnel_source_state: str,
) -> tuple[MetricValue, dict[str, int]]:
    entities, unknown_with_stock, rows_with_quantity = _collect_stock_entities(normalized_bundle)
    diagnostics = {
        "stock_entities_with_positive_units": len(entities),
        "stock_rows_with_quantity": rows_with_quantity,
        "stock_entities_without_id": unknown_with_stock,
        "resolved_entities": 0,
        "unresolved_entities": 0,
    }

    if not _source_usable(stock_source_state):
        return (
            _metric(None, status=MetricStatus.UNAVAILABLE, source="stocks", note="stocks source unavailable for dead stock"),
            diagnostics,
        )

    if not entities:
        if unknown_with_stock > 0:
            return (
                _metric(None, status=MetricStatus.PARTIAL, source="stocks", note="stock rows with quantity have no stable entity id"),
                diagnostics,
            )
        status = MetricStatus.PARTIAL if stock_source_state == "partial" else MetricStatus.CONFIRMED
        return (_metric(0, status=status, source="health_policy_v1", note="no positive stock entities"), diagnostics)

    if not _source_usable(funnel_source_state):
        return (
            _metric(None, status=MetricStatus.PARTIAL, source="funnel", note="funnel source unavailable for dead stock evaluation"),
            diagnostics,
        )

    movement = _collect_funnel_movement(normalized_bundle)
    dead_count = 0
    unresolved = 0
    resolved = 0
    for entity in entities:
        movement_value = movement.get(entity)
        if movement_value is None:
            unresolved += 1
            continue
        resolved += 1
        if movement_value <= 0:
            dead_count += 1

    diagnostics["resolved_entities"] = resolved
    diagnostics["unresolved_entities"] = unresolved

    if resolved == 0:
        return (
            _metric(None, status=MetricStatus.PARTIAL, source="health_policy_v1", note="no resolved entity movement for dead stock"),
            diagnostics,
        )

    status = MetricStatus.CONFIRMED
    if stock_source_state == "partial" or funnel_source_state == "partial" or unresolved > 0 or unknown_with_stock > 0:
        status = MetricStatus.PARTIAL

    note = f"dead stock entities={dead_count}, resolved={resolved}, unresolved={unresolved}"
    return (_metric(dead_count, status=status, source="health_policy_v1", note=note), diagnostics)


def _overstock_metric(
    *,
    normalized_bundle: NormalizedBundle,
    stock_source_state: str,
    funnel_source_state: str,
) -> tuple[MetricValue, dict[str, int]]:
    entities, unknown_with_stock, _ = _collect_stock_entities(normalized_bundle)
    diagnostics = {
        "stock_entities_with_positive_units": len(entities),
        "stock_entities_without_id": unknown_with_stock,
        "resolved_entities": 0,
        "unresolved_entities": 0,
    }

    if not _source_usable(stock_source_state):
        return (
            _metric(None, status=MetricStatus.UNAVAILABLE, source="stocks", note="stocks source unavailable for overstock"),
            diagnostics,
        )

    if not entities:
        if unknown_with_stock > 0:
            return (
                _metric(None, status=MetricStatus.PARTIAL, source="stocks", note="stock rows with quantity have no stable entity id"),
                diagnostics,
            )
        status = MetricStatus.PARTIAL if stock_source_state == "partial" else MetricStatus.CONFIRMED
        return (_metric(0, status=status, source="health_policy_v1", note="no positive stock entities"), diagnostics)

    if not _source_usable(funnel_source_state):
        return (
            _metric(None, status=MetricStatus.PARTIAL, source="funnel", note="funnel source unavailable for overstock evaluation"),
            diagnostics,
        )

    movement = _collect_funnel_movement(normalized_bundle)
    threshold = float(HEALTH_POLICY_V1["stock_thresholds"]["overstock_days_cover"])
    overstock_count = 0
    unresolved = 0
    resolved = 0

    for entity, quantity in entities.items():
        movement_value = movement.get(entity)
        if movement_value is None:
            unresolved += 1
            continue
        resolved += 1
        if movement_value <= 0:
            continue
        days_cover = quantity / movement_value
        if days_cover >= threshold:
            overstock_count += 1

    diagnostics["resolved_entities"] = resolved
    diagnostics["unresolved_entities"] = unresolved

    if resolved == 0:
        return (
            _metric(None, status=MetricStatus.PARTIAL, source="health_policy_v1", note="no resolved movement for overstock"),
            diagnostics,
        )

    status = MetricStatus.CONFIRMED
    if stock_source_state == "partial" or funnel_source_state == "partial" or unresolved > 0 or unknown_with_stock > 0:
        status = MetricStatus.PARTIAL

    note = f"overstock entities={overstock_count}, threshold_days_cover={threshold}, resolved={resolved}, unresolved={unresolved}"
    return (_metric(overstock_count, status=status, source="health_policy_v1", note=note), diagnostics)


def _problematic_sku_metric(
    *,
    dead_stock_metric: MetricValue,
    overstock_metric: MetricValue,
    stock: StockMetricsSection | None,
) -> MetricValue:
    out_of_stock_metric = stock.out_of_stock_items_count if stock is not None else _metric(
        None,
        status=MetricStatus.UNAVAILABLE,
        source="stock",
        note="stock section is missing",
    )

    values = [
        _to_float(dead_stock_metric.value),
        _to_float(overstock_metric.value),
        _to_float(out_of_stock_metric.value),
    ]
    known_values = [value for value in values if value is not None]

    if not known_values:
        status = _status_from_metric_values([dead_stock_metric, overstock_metric, out_of_stock_metric])
        if status != MetricStatus.UNAVAILABLE:
            status = MetricStatus.PARTIAL
        return _metric(None, status=status, source="health_policy_v1", note="problematic SKU evidence is insufficient")

    total = int(round(sum(known_values)))
    status = _status_from_metric_values([dead_stock_metric, overstock_metric, out_of_stock_metric])
    if len(known_values) < 3:
        status = MetricStatus.PARTIAL
        note = "problematic_sku_count is a lower bound due to missing sub-signals"
    else:
        note = None

    return _metric(total, status=status, source="health_policy_v1", note=note)


def _sku_health_signals_metric(
    *,
    dead_stock_metric: MetricValue,
    overstock_metric: MetricValue,
    stock: StockMetricsSection | None,
) -> MetricValue:
    out_of_stock_metric = stock.out_of_stock_items_count if stock is not None else _metric(
        None,
        status=MetricStatus.UNAVAILABLE,
        source="stock",
        note="stock section is missing",
    )

    values = [
        _to_float(dead_stock_metric.value),
        _to_float(overstock_metric.value),
        _to_float(out_of_stock_metric.value),
    ]
    known_values = [value for value in values if value is not None]
    if not known_values:
        status = _status_from_metric_values([dead_stock_metric, overstock_metric, out_of_stock_metric])
        if status != MetricStatus.UNAVAILABLE:
            status = MetricStatus.PARTIAL
        return _metric(None, status=status, source="health_policy_v1", note="SKU health signals are unavailable")

    signal_count = 0
    if values[0] is not None and values[0] > 0:
        signal_count += 1
    if values[1] is not None and values[1] > 0:
        signal_count += 1
    if values[2] is not None and values[2] > 0:
        signal_count += 1

    status = _status_from_metric_values([dead_stock_metric, overstock_metric, out_of_stock_metric])
    if len(known_values) < 3:
        status = MetricStatus.PARTIAL

    return _metric(signal_count, status=status, source="health_policy_v1", note="count of active SKU risk signals")


def _business_health_metric(components: dict[str, MetricValue]) -> tuple[MetricValue, str | None]:
    max_scores = dict(HEALTH_POLICY_V1["component_max_scores"])
    available = {name: metric for name, metric in components.items() if metric.value is not None}
    missing_components = [name for name in components.keys() if name not in available]

    if not available:
        return (
            _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="all health components are unavailable"),
            "business health score unavailable: all components are unavailable",
        )

    raw_score = 0.0
    max_score = 0.0
    for name, metric in available.items():
        value = _to_float(metric.value)
        if value is None:
            continue
        raw_score += value
        max_score += float(max_scores.get(name, 0.0))

    if max_score <= 0:
        return (
            _metric(None, status=MetricStatus.UNAVAILABLE, source="health_policy_v1", note="invalid health component maxima"),
            "business health score unavailable: invalid component maxima",
        )

    score = (raw_score / max_score) * 100.0
    if missing_components:
        penalty = float(HEALTH_POLICY_V1["score_missing_component_penalty"]) * len(missing_components)
        score *= max(0.0, 1.0 - penalty)

    status = MetricStatus.CONFIRMED
    statuses = {str(metric.status) for metric in components.values()}
    if missing_components or MetricStatus.PARTIAL.value in statuses or MetricStatus.UNAVAILABLE.value in statuses:
        status = MetricStatus.PARTIAL

    score = round(_clamp(score, 0.0, 100.0), 2)
    note = "business health score from weighted component normalization"
    status_note = "business health score is confirmed"
    if status != MetricStatus.CONFIRMED:
        status_note = (
            "business health score is partial; missing components="
            + str(missing_components)
        )

    return (_metric(score, status=status, source="health_policy_v1", note=note), status_note)


def assemble_health_metrics(
    *,
    normalized_bundle: NormalizedBundle,
    financial: FinancialMetricsSection | None,
    funnel: FunnelMetricsSection | None,
    ads: AdsMetricsSection | None,
    stock: StockMetricsSection | None,
) -> HealthMetricsSection:
    profitability_component = _profitability_component(financial)
    ads_component = _ads_component(ads)
    funnel_component = _funnel_component(funnel)
    stock_component = _stock_component(stock)

    base_components = {
        "profitability": profitability_component,
        "ads": ads_component,
        "funnel": funnel_component,
        "stock": stock_component,
    }
    data_quality_component = _data_quality_component(base_components)

    components = dict(base_components)
    components["data_quality"] = data_quality_component

    business_health_score, status_note = _business_health_metric(components)

    stock_source_state = _source_state(normalized_bundle, "stocks")
    funnel_source_state = _source_state(normalized_bundle, "funnel")
    dead_stock_metric, dead_diag = _dead_stock_metric(
        normalized_bundle=normalized_bundle,
        stock_source_state=stock_source_state,
        funnel_source_state=funnel_source_state,
    )
    overstock_metric, overstock_diag = _overstock_metric(
        normalized_bundle=normalized_bundle,
        stock_source_state=stock_source_state,
        funnel_source_state=funnel_source_state,
    )

    problematic_sku_count = _problematic_sku_metric(
        dead_stock_metric=dead_stock_metric,
        overstock_metric=overstock_metric,
        stock=stock,
    )
    sku_health_signals_count = _sku_health_signals_metric(
        dead_stock_metric=dead_stock_metric,
        overstock_metric=overstock_metric,
        stock=stock,
    )

    warnings: list[str] = []
    for metric_name, metric in components.items():
        if metric.note:
            append_warning(warnings, f"{metric_name}: {metric.note}", namespace="health")
    for metric_name, metric in {
        "dead_stock_risk_count": dead_stock_metric,
        "overstock_risk_count": overstock_metric,
        "problematic_sku_count": problematic_sku_count,
        "sku_health_signals_count": sku_health_signals_count,
    }.items():
        if metric.note:
            append_warning(warnings, f"{metric_name}: {metric.note}", namespace="health")
    warnings = dedupe_warnings(warnings)

    source_quality = {
        "sales": _source_state(normalized_bundle, "sales"),
        "realization": _source_state(normalized_bundle, "realization"),
        "funnel": funnel_source_state,
        "ads_campaigns": _source_state(normalized_bundle, "ads_campaigns"),
        "ads_stats": _source_state(normalized_bundle, "ads_stats"),
        "stocks": stock_source_state,
    }

    diagnostics = {
        "policy": HEALTH_POLICY_V1,
        "components_status": {name: metric.status for name, metric in components.items()},
        "components_values": {name: metric.value for name, metric in components.items()},
        "business_health_score_status": business_health_score.status,
        "business_health_score_value": business_health_score.value,
        "dead_stock_eval": dead_diag,
        "overstock_eval": overstock_diag,
    }

    note = "health metrics are explainable and rule-based"
    if str(business_health_score.status) != MetricStatus.CONFIRMED.value:
        note = "health metrics are partial due to incomplete component evidence"

    return HealthMetricsSection(
        business_health_score=business_health_score,
        sku_health_signals_count=sku_health_signals_count,
        problematic_sku_count=problematic_sku_count,
        dead_stock_risk_count=dead_stock_metric,
        overstock_risk_count=overstock_metric,
        business_health_status_note=status_note,
        component_scores=components,
        source_quality=source_quality,
        diagnostics=diagnostics,
        warnings=warnings,
        note=note,
    )


__all__ = ["assemble_health_metrics", "HEALTH_POLICY_V1"]
