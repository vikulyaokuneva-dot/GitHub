from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_pct(value: Any) -> float | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    if 0 <= parsed <= 1:
        return parsed * 100.0
    return parsed


DEFAULT_HEALTH_THRESHOLDS: Dict[str, float] = {
    "orders_strong": 10.0,
    "orders_ok": 3.0,
    "orders_min": 1.0,
    "buyout_rate_strong": 0.85,
    "buyout_rate_ok": 0.65,
    "buyout_rate_weak": 0.4,
    "margin_strong_pct": 25.0,
    "margin_ok_pct": 12.0,
    "margin_weak_pct": 5.0,
    "ads_roi_strong_pct": 120.0,
    "ads_roi_ok_pct": 80.0,
    "ddr_strong_pct": 20.0,
    "ddr_ok_pct": 35.0,
    "min_available_weight": 4.0,
    "risk_max_score": 4.0,
    "unstable_max_score": 6.5,
    "healthy_max_score": 8.5,
}

HEALTH_WEIGHTS: Dict[str, float] = {
    "orders": 2.0,
    "buyout": 1.5,
    "profit": 2.5,
    "margin": 1.5,
    "funnel": 1.5,
    "ads": 1.0,
}

HEALTH_STATUS_TO_LEGACY: Dict[str, str] = {
    "risk": "LIQUIDATE",
    "unstable": "WATCH",
    "healthy": "FIX",
    "strong": "SCALE",
}


def _extract_sku_rows(metrics: Any) -> List[Dict[str, Any]]:
    if isinstance(metrics, list):
        return [row for row in metrics if isinstance(row, dict)]
    if not isinstance(metrics, dict):
        return []

    candidates = ["sku_metrics", "items", "skus"]
    for key in candidates:
        value = metrics.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    value = metrics.get("metrics_by_sku")
    if isinstance(value, dict):
        rows: List[Dict[str, Any]] = []
        for sku, payload in value.items():
            if isinstance(payload, dict):
                row = dict(payload)
                row.setdefault("sku", str(sku))
                rows.append(row)
        return rows
    return []


def _resolve_thresholds(overrides: Mapping[str, Any] | None = None) -> Dict[str, float]:
    resolved = dict(DEFAULT_HEALTH_THRESHOLDS)
    if not isinstance(overrides, Mapping):
        return resolved
    for key, fallback in DEFAULT_HEALTH_THRESHOLDS.items():
        parsed = _as_float(overrides.get(key))
        if parsed is None:
            resolved[key] = float(fallback)
        else:
            resolved[key] = float(parsed)
    return resolved


def _append_unique(bucket: List[str], value: str) -> None:
    token = str(value or "").strip()
    if token and token not in bucket:
        bucket.append(token)


def _extract_funnel_by_sku(metrics: Any, explicit_diagnostics: Any = None) -> Dict[str, Dict[str, Any]]:
    diagnostics = explicit_diagnostics if isinstance(explicit_diagnostics, dict) else {}
    if not diagnostics and isinstance(metrics, dict):
        diagnostics = metrics.get("sales_funnel_diagnostics", {})
    if not diagnostics and isinstance(metrics, dict):
        sales_funnel = metrics.get("sales_funnel", {})
        if isinstance(sales_funnel, dict):
            diagnostics = sales_funnel.get("sku_diagnostics", {})
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    rows = diagnostics.get("items", [])
    if not isinstance(rows, list):
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if sku:
            out[sku] = row
    return out


def _merge_rows(primary_rows: List[Dict[str, Any]], fallback_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not fallback_rows:
        return [dict(row) for row in primary_rows if isinstance(row, dict)]

    merged: Dict[str, Dict[str, Any]] = {}
    for row in fallback_rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or row.get("nm_id") or row.get("offer_id") or "").strip()
        if not sku:
            continue
        merged[sku] = dict(row)

    for row in primary_rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or row.get("nm_id") or row.get("offer_id") or "").strip()
        if not sku:
            continue
        dst = merged.get(sku, {})
        for key, value in row.items():
            if dst.get(key) in (None, "") and value not in (None, ""):
                dst[key] = value
            elif key not in dst:
                dst[key] = value
        dst.setdefault("sku", sku)
        merged[sku] = dst
    return list(merged.values())


def _normalize_margin_pct(row: Dict[str, Any]) -> float | None:
    margin = _as_pct(row.get("margin_pct"))
    if margin is None:
        margin = _as_pct(row.get("margin"))
    if margin is None:
        margin = _as_pct(row.get("profitability_pct"))
    return margin


def _normalize_orders(row: Dict[str, Any]) -> float | None:
    orders = _as_float(row.get("orders"))
    if orders is None:
        orders = _as_float(row.get("orders_count"))
    if orders is None:
        orders = _as_float(row.get("sales_count"))
    return orders


def _normalize_buyouts(row: Dict[str, Any]) -> float | None:
    buyouts = _as_float(row.get("buyouts"))
    if buyouts is None:
        buyouts = _as_float(row.get("buys"))
    if buyouts is None:
        buyouts = _as_float(row.get("sales"))
    return buyouts


def _score_orders(
    row: Dict[str, Any],
    factors: List[str],
    warnings: List[str],
    thresholds: Dict[str, float],
) -> tuple[float, bool]:
    orders = _normalize_orders(row)
    if orders is None:
        _append_unique(factors, "orders_missing")
        _append_unique(warnings, "orders_missing")
        return 0.0, False
    if orders >= thresholds["orders_strong"]:
        _append_unique(factors, "stable_orders")
        return 1.0, True
    if orders >= thresholds["orders_ok"]:
        _append_unique(factors, "orders_ok")
        return 0.75, True
    if orders >= thresholds["orders_min"]:
        _append_unique(factors, "low_orders")
        return 0.45, True
    _append_unique(factors, "no_orders")
    return 0.0, True


def _score_buyout(
    row: Dict[str, Any],
    factors: List[str],
    warnings: List[str],
    thresholds: Dict[str, float],
) -> tuple[float, bool]:
    orders = _normalize_orders(row)
    buyouts = _normalize_buyouts(row)
    if orders is None:
        _append_unique(factors, "orders_missing_for_buyout_rate")
        _append_unique(warnings, "buyout_rate_missing")
        return 0.0, False
    if orders <= 0:
        _append_unique(factors, "no_orders")
        return 0.0, True
    if buyouts is None:
        _append_unique(factors, "buyouts_missing")
        _append_unique(warnings, "buyouts_missing")
        return 0.0, False
    buyout_rate = float(buyouts) / float(orders)
    if buyout_rate >= thresholds["buyout_rate_strong"]:
        _append_unique(factors, "healthy_buyout_rate")
        return 1.0, True
    if buyout_rate >= thresholds["buyout_rate_ok"]:
        _append_unique(factors, "buyout_rate_ok")
        return 0.7, True
    if buyout_rate >= thresholds["buyout_rate_weak"]:
        _append_unique(factors, "weak_buyout_rate")
        return 0.35, True
    _append_unique(factors, "critical_buyout_rate")
    return 0.1, True


def _score_profit(row: Dict[str, Any], factors: List[str], warnings: List[str]) -> tuple[float, bool]:
    profit = _as_float(row.get("profit"))
    if profit is None:
        profit = _as_float(row.get("net_profit"))
    if profit is None:
        _append_unique(factors, "profit_missing")
        _append_unique(warnings, "profit_missing")
        return 0.0, False
    if profit > 0:
        _append_unique(factors, "strong_profitability")
        return 1.0, True
    if profit == 0:
        _append_unique(factors, "zero_profit")
        return 0.4, True
    _append_unique(factors, "negative_profit")
    return 0.0, True


def _score_margin(
    row: Dict[str, Any],
    factors: List[str],
    warnings: List[str],
    thresholds: Dict[str, float],
) -> tuple[float, bool]:
    margin_pct = _normalize_margin_pct(row)
    if margin_pct is None:
        _append_unique(factors, "margin_missing")
        _append_unique(warnings, "margin_missing")
        return 0.0, False
    if margin_pct >= thresholds["margin_strong_pct"]:
        _append_unique(factors, "healthy_margin")
        return 1.0, True
    if margin_pct >= thresholds["margin_ok_pct"]:
        _append_unique(factors, "margin_ok")
        return 0.7, True
    if margin_pct >= thresholds["margin_weak_pct"]:
        _append_unique(factors, "low_margin")
        return 0.4, True
    _append_unique(factors, "critical_margin")
    return 0.1, True


def _score_funnel(
    funnel_item: Dict[str, Any],
    factors: List[str],
    warnings: List[str],
) -> tuple[float, bool]:
    issue_type = str(funnel_item.get("issue_type") or "").strip()
    if not issue_type:
        _append_unique(factors, "funnel_missing")
        _append_unique(warnings, "funnel_missing")
        return 0.0, False
    if issue_type == "healthy_funnel":
        _append_unique(factors, "healthy_funnel")
        return 1.0, True
    if issue_type == "insufficient_data":
        _append_unique(factors, "funnel_insufficient_data")
        _append_unique(warnings, "funnel_insufficient_data")
        return 0.0, False
    _append_unique(factors, "weak_funnel")
    _append_unique(factors, f"funnel_{issue_type}")
    return 0.2, True


def _ads_score(
    row: Dict[str, Any],
    factors: List[str],
    warnings: List[str],
    thresholds: Dict[str, float],
) -> tuple[float, bool]:
    ads_spend = _as_float(row.get("ads_spend"))
    if ads_spend is None:
        _append_unique(factors, "ads_data_missing")
        return 0.0, False
    if ads_spend <= 0:
        _append_unique(factors, "no_ads_activity")
        return 0.6, True

    orders = _normalize_orders(row)
    if orders is not None and orders <= 0:
        _append_unique(factors, "ads_without_orders")
        return 0.1, True

    roi = _as_pct(row.get("roi"))
    if roi is None:
        roi = _as_pct(row.get("ads_roi"))
    ddr = _as_pct(row.get("ddr"))

    if roi is not None:
        if roi >= thresholds["ads_roi_strong_pct"]:
            _append_unique(factors, "strong_ads_efficiency")
            return 1.0, True
        if roi >= thresholds["ads_roi_ok_pct"]:
            _append_unique(factors, "ads_efficiency_ok")
            return 0.7, True
        _append_unique(factors, "weak_ads_efficiency")
        return 0.3, True

    if ddr is not None:
        if ddr <= thresholds["ddr_strong_pct"]:
            _append_unique(factors, "strong_ads_efficiency")
            return 1.0, True
        if ddr <= thresholds["ddr_ok_pct"]:
            _append_unique(factors, "ads_efficiency_ok")
            return 0.7, True
        _append_unique(factors, "weak_ads_efficiency")
        return 0.3, True

    if orders is not None and orders > 0:
        _append_unique(factors, "ads_with_orders")
        _append_unique(warnings, "ads_efficiency_partial")
        return 0.65, True

    _append_unique(factors, "weak_ads_efficiency")
    _append_unique(warnings, "ads_efficiency_partial")
    return 0.2, True


def _resolve_health_status(score: float, thresholds: Dict[str, float]) -> str:
    if score < thresholds["risk_max_score"]:
        return "risk"
    if score < thresholds["unstable_max_score"]:
        return "unstable"
    if score < thresholds["healthy_max_score"]:
        return "healthy"
    return "strong"


def _status_actions(status: str) -> List[Dict[str, str]]:
    if status == "LIQUIDATE":
        return [
            {
                "priority": "P1",
                "title": "Снижение цены/распродажа остатков",
                "details": "Ускорить оборачиваемость и высвободить капитал.",
            },
            {
                "priority": "P2",
                "title": "Отключить рекламу",
                "details": "Остановить неэффективные кампании до пересмотра unit-экономики.",
            },
            {
                "priority": "P3",
                "title": "Решение: вывести из ассортимента",
                "details": "Проверить целесообразность дальнейших закупок SKU.",
            },
        ]
    if status == "FIX":
        return [
            {
                "priority": "P1",
                "title": "Поднять маржу/проверить цену и себестоимость",
                "details": "Пересчитать юнит-экономику и целевую цену.",
            },
            {
                "priority": "P2",
                "title": "Оптимизировать карточку (конверсия)",
                "details": "Улучшить контент, фото, оффер и отзывы.",
            },
            {
                "priority": "P3",
                "title": "Точечная реклама/ключи",
                "details": "Оставить только высокоинтентные запросы и связки.",
            },
        ]
    if status == "SCALE":
        return [
            {
                "priority": "P1",
                "title": "Масштабировать трафик/рекламу",
                "details": "Увеличивать бюджет ступенчато с контролем ROMI/DDR.",
            },
            {
                "priority": "P2",
                "title": "Проверить остатки и поставку",
                "details": "Не допускать OOS при росте продаж.",
            },
            {
                "priority": "P3",
                "title": "Расширить ключи/органику",
                "details": "Укрепить поисковое покрытие и SEO карточки.",
            },
        ]
    return [
        {
            "priority": "P1",
            "title": "Собрать больше данных",
            "details": "Недостаточно статистики для уверенного решения.",
        },
        {
            "priority": "P2",
            "title": "Мини-тест рекламы",
            "details": "Запустить ограниченный тест и измерить эффективность.",
        },
        {
            "priority": "P3",
            "title": "Проверить остатки/дефицит",
            "details": "Исключить влияние out-of-stock на динамику SKU.",
        },
    ]


def _build_item(
    row: Dict[str, Any],
    funnel_item: Dict[str, Any],
    thresholds: Dict[str, float],
) -> Tuple[Dict[str, Any], float]:
    sku = str(row.get("sku") or row.get("nm_id") or row.get("offer_id") or "").strip()
    if not sku:
        sku = "unknown_sku"

    factors: List[str] = []
    warnings: List[str] = []
    component_debug: Dict[str, Any] = {}

    weighted_score = 0.0
    available_weight = 0.0
    missing_components = 0

    components = {
        "orders": _score_orders(row, factors, warnings, thresholds),
        "buyout": _score_buyout(row, factors, warnings, thresholds),
        "profit": _score_profit(row, factors, warnings),
        "margin": _score_margin(row, factors, warnings, thresholds),
        "funnel": _score_funnel(funnel_item if isinstance(funnel_item, dict) else {}, factors, warnings),
        "ads": _ads_score(row, factors, warnings, thresholds),
    }

    for key, (value, available) in components.items():
        weight = float(HEALTH_WEIGHTS.get(key, 0.0))
        component_debug[key] = {
            "available": bool(available),
            "weight": weight,
            "value": round(float(value), 4),
        }
        if available:
            available_weight += weight
            weighted_score += float(value) * weight
        else:
            missing_components += 1

    if available_weight > 0:
        health_score = round((weighted_score / available_weight) * 10.0, 2)
    else:
        health_score = 0.0

    scoring_status = "ok"
    if available_weight < thresholds["min_available_weight"]:
        scoring_status = "insufficient_data"
        _append_unique(warnings, "insufficient_data")
        health_score = min(float(health_score), 4.5)

    health_score = max(0.0, min(10.0, health_score))
    health_status = _resolve_health_status(health_score, thresholds)
    status = HEALTH_STATUS_TO_LEGACY.get(health_status, "WATCH")

    if scoring_status != "ok" or missing_components >= 3:
        confidence = "low"
    elif missing_components > 0:
        confidence = "medium"
    else:
        confidence = "high"

    profit = _as_float(row.get("profit"))
    if profit is None:
        profit = _as_float(row.get("net_profit"))
    if profit is None:
        profit = 0.0

    item = {
        "sku": sku,
        "health_score": round(float(health_score), 2),
        "health_status": health_status,
        "status": status,
        "scoring_status": scoring_status,
        "confidence": confidence,
        "factors": factors[:12],
        "warnings": warnings[:8],
        "reasons": factors[:8],
        "components": component_debug,
        "actions": _status_actions(status),
    }
    return item, profit


def compute_sku_health(
    facts: Dict[str, Any],
    metrics: Dict[str, Any],
    *,
    sku_rows: Any = None,
    sales_funnel_diagnostics: Any = None,
    thresholds: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    resolved_thresholds = _resolve_thresholds(thresholds)
    rows = _extract_sku_rows(metrics)
    fallback_rows = _extract_sku_rows(sku_rows)
    rows = _merge_rows(rows, fallback_rows)
    funnel_by_sku = _extract_funnel_by_sku(metrics, explicit_diagnostics=sales_funnel_diagnostics)

    items: List[Dict[str, Any]] = []
    scored_items: List[Dict[str, Any]] = []
    legacy_statuses = {"SCALE": 0, "FIX": 0, "WATCH": 0, "LIQUIDATE": 0}
    status_counts = {"risk": 0, "unstable": 0, "healthy": 0, "strong": 0}
    confidences = {"high": 0, "medium": 0, "low": 0}
    scored_sku_count = 0
    insufficient_data_count = 0
    sum_scores = 0.0

    for row in rows:
        sku = str(row.get("sku") or row.get("nm_id") or row.get("offer_id") or "").strip()
        funnel_item = funnel_by_sku.get(sku, {})
        item, profit = _build_item(row, funnel_item, resolved_thresholds)
        items.append(item)
        legacy_statuses[item["status"]] = legacy_statuses.get(item["status"], 0) + 1
        status_counts[item["health_status"]] = status_counts.get(item["health_status"], 0) + 1
        confidences[item["confidence"]] = confidences.get(item["confidence"], 0) + 1
        if item.get("scoring_status") == "ok":
            scored_sku_count += 1
            sum_scores += float(item.get("health_score", 0.0) or 0.0)
        else:
            insufficient_data_count += 1
        scored_items.append(
            {
                "sku": item["sku"],
                "score": item["health_score"],
                "health_status": item["health_status"],
                "status": item["status"],
                "profit": round(profit, 2),
                "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
            }
        )

    summary_reasons: List[str] = []
    if not rows:
        summary_reasons.append("SKU-level metrics not found in metrics payload")
        confidence = "low"
    elif confidences["low"] > 0:
        confidence = "low"
    elif confidences["medium"] > 0:
        confidence = "medium"
    else:
        confidence = "high"

    if not rows or scored_sku_count == 0:
        summary_status = "insufficient_data"
    elif scored_sku_count < len(rows):
        summary_status = "partial"
        summary_reasons.append("Some SKU health scores were computed with insufficient inputs")
    else:
        summary_status = "ok"

    average_health_score = round(sum_scores / scored_sku_count, 2) if scored_sku_count > 0 else None

    top_scale = sorted(
        [x for x in scored_items if x["status"] == "SCALE"],
        key=lambda x: (x["score"], x["profit"], str(x["sku"])),
        reverse=True,
    )[:3]
    top_liquidate = sorted(
        [x for x in scored_items if x["status"] == "LIQUIDATE"],
        key=lambda x: (x["score"], x["profit"], str(x["sku"])),
    )[:3]
    top_risk_sku = sorted(
        [x for x in scored_items if x.get("health_status") == "risk"],
        key=lambda x: (x["score"], x["profit"], str(x["sku"])),
    )[:5]
    top_strong_sku = sorted(
        [x for x in scored_items if x.get("health_status") == "strong"],
        key=lambda x: (x["score"], x["profit"], str(x["sku"])),
        reverse=True,
    )[:5]

    top_level_warnings: List[str] = []

    def _add_warning(value: Any) -> None:
        token = str(value or "").strip()
        if token and token not in top_level_warnings:
            top_level_warnings.append(token)

    for reason in summary_reasons:
        _add_warning(reason)
    if summary_status == "insufficient_data":
        _add_warning("insufficient_data")
    elif summary_status == "partial":
        _add_warning("partial_data")
    for item in items:
        warnings_list = item.get("warnings", [])
        if not isinstance(warnings_list, list):
            continue
        for warning_code in warnings_list:
            _add_warning(warning_code)
        if len(top_level_warnings) >= 32:
            break

    return {
        "generated_at": _utc_now_iso(),
        "seller_id": str(facts.get("seller_id") or "unknown_seller"),
        "date": str(facts.get("run_date") or facts.get("date") or ""),
        "status": summary_status,
        "warnings": top_level_warnings,
        "thresholds": resolved_thresholds,
        "items": items,
        "summary": {
            "status": summary_status,
            "sku_count": len(items),
            "scored_sku_count": scored_sku_count,
            "insufficient_data_count": insufficient_data_count,
            "status_counts": status_counts,
            "average_health_score": average_health_score,
            "top_risk_sku": top_risk_sku,
            "top_strong_sku": top_strong_sku,
            "total_skus": len(items),
            "SCALE": legacy_statuses["SCALE"],
            "FIX": legacy_statuses["FIX"],
            "WATCH": legacy_statuses["WATCH"],
            "LIQUIDATE": legacy_statuses["LIQUIDATE"],
            "confidence": confidence,
            "reasons": summary_reasons,
            "top_scale": top_scale,
            "top_liquidate": top_liquidate,
        },
    }
