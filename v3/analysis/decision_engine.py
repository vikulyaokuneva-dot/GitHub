from __future__ import annotations

from typing import Any, Dict, List

from ..analytics.sales_funnel import FUNNEL_ISSUE_REASONS_RU


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_sku_metrics(metrics: Any) -> List[Dict[str, Any]]:
    if isinstance(metrics, list):
        return [x for x in metrics if isinstance(x, dict)]
    if isinstance(metrics, dict):
        value = metrics.get("sku_metrics")
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _extract_abc(abc: Any) -> List[Dict[str, Any]]:
    if isinstance(abc, list):
        return [x for x in abc if isinstance(x, dict)]
    if isinstance(abc, dict):
        value = abc.get("items")
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _extract_health_items(health: Any) -> List[Dict[str, Any]]:
    if isinstance(health, dict):
        value = health.get("items")
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _extract_territorial_items(territorial: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(territorial, dict):
        return {}
    value = territorial.get("skus")
    if not isinstance(value, list):
        value = territorial.get("items")
    if not isinstance(value, list):
        return {}
    rows: Dict[str, Dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if sku:
            rows[sku] = item
    return rows


def _extract_logistics_items(logistics: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(logistics, dict):
        return {}
    value = logistics.get("skus")
    if not isinstance(value, list):
        value = logistics.get("items")
    if not isinstance(value, list):
        return {}
    rows: Dict[str, Dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if sku:
            rows[sku] = item
    return rows


def _extract_funnel_by_sku(metrics: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(metrics, dict):
        return {}

    diagnostics = metrics.get("sales_funnel_diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = (
            (metrics.get("sales_funnel") or {}).get("sku_diagnostics")
            if isinstance(metrics.get("sales_funnel"), dict)
            else {}
        )
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    items = diagnostics.get("items")
    if not isinstance(items, list):
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if sku:
            out[sku] = item
    return out


def _extract_funnel_summary(metrics: Any) -> Dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    diagnostics = metrics.get("sales_funnel_diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = (
            (metrics.get("sales_funnel") or {}).get("sku_diagnostics")
            if isinstance(metrics.get("sales_funnel"), dict)
            else {}
        )
    if not isinstance(diagnostics, dict):
        return {}
    summary = diagnostics.get("summary")
    return summary if isinstance(summary, dict) else {}


def _extract_profit_contribution(metrics: Any) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(metrics, dict):
        return {}, {}
    payload = metrics.get("profit_contribution")
    if not isinstance(payload, dict):
        return {}, {}

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    rows = payload.get("items")
    if not isinstance(rows, list):
        rows = []
        for key, group in (("p1", "P1"), ("p2", "P2"), ("p3", "P3"), ("p4", "P4")):
            candidates = payload.get(key, [])
            if not isinstance(candidates, list):
                continue
            for row in candidates:
                if not isinstance(row, dict):
                    continue
                patched = dict(row)
                patched.setdefault("profit_group", group)
                rows.append(patched)

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if sku:
            out[sku] = row
    return out, summary


def _extract_keyword_monitoring(metrics: Any) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(metrics, dict):
        return {}, {}
    payload = metrics.get("keyword_monitoring")
    if not isinstance(payload, dict):
        return {}, {}

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    rows = payload.get("sku_items")
    if not isinstance(rows, list):
        rows = payload.get("sku_summary")
    if not isinstance(rows, list):
        rows = []

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if sku:
            out[sku] = row
    return out, summary


def _keyword_signals_for_sku_ru(keyword_row: Dict[str, Any]) -> List[str]:
    if not isinstance(keyword_row, dict):
        return []
    signals: List[str] = []
    winner_count = int(keyword_row.get("winner_queries_count", 0) or 0)
    growth_count = int(keyword_row.get("growth_queries_count", 0) or 0)
    weak_count = int(keyword_row.get("weak_queries_count", 0) or 0)
    costly_count = int(keyword_row.get("costly_queries_count", 0) or 0)
    health_status = str(keyword_row.get("keyword_health_status") or "").strip().lower()

    if costly_count > 0:
        signals.append("Есть дорогие запросы с плохой эффективностью.")
    if weak_count > 0:
        signals.append("SKU получает трафик по запросам, которые не конвертируются в заказы.")
    if growth_count > 0:
        signals.append("Есть перспективные запросы с хорошей конверсией, но низким объемом показов.")
    if winner_count > 0:
        signals.append("Есть сильные поисковые запросы, которые можно масштабировать.")
    if health_status in {"risk", "unstable"} and not signals:
        signals.append("По SKU есть признаки нерелевантного поискового трафика.")
    return signals[:3]


def _keyword_global_signal_ru(summary: Dict[str, Any]) -> str:
    if not isinstance(summary, dict):
        return ""
    winner_count = int(summary.get("winner_query_count", 0) or 0)
    growth_count = int(summary.get("growth_query_count", 0) or 0)
    low_relevance_count = int(summary.get("low_relevance_query_count", 0) or 0)
    no_orders_count = int(summary.get("no_orders_query_count", 0) or 0)
    costly_count = int(summary.get("costly_query_count", 0) or 0)

    if costly_count > 0 and costly_count >= max(1, winner_count):
        return "Есть дорогие запросы с плохой эффективностью."
    if (low_relevance_count + no_orders_count) > max(2, winner_count):
        return "Часть запросов дает показы, но не дает коммерческого результата."
    if growth_count > 0:
        return "Есть перспективные запросы с хорошей конверсией, но низким объемом показов."
    if winner_count > 0:
        return "Есть сильные поисковые запросы, которые можно масштабировать."
    return ""


def _profit_group_signal_ru(profit_group: str) -> str:
    group = str(profit_group or "").strip().upper()
    if group == "P1":
        return "Этот SKU является драйвером прибыли."
    if group == "P2":
        return "Этот SKU поддерживает прибыль и требует контроля эффективности."
    if group == "P3":
        return "Этот SKU близок к точке безубыточности."
    if group == "P4":
        return "Этот SKU приносит убыток и требует внимания."
    return ""


def _profit_concentration_signal_ru(summary: Dict[str, Any]) -> str:
    if not isinstance(summary, dict):
        return ""
    label = str(summary.get("profit_concentration") or "").strip().lower()
    top_20_share = _as_float_or_none(summary.get("top_20_profit_share"))

    if label == "high" or (top_20_share is not None and top_20_share >= 0.80):
        return "Бизнес сильно зависит от небольшого числа SKU."
    if label == "medium" or (top_20_share is not None and top_20_share >= 0.60):
        return "Прибыль умеренно концентрирована в ограниченном числе SKU."
    if label == "low":
        return "Прибыль распределена относительно равномерно."
    return ""


def _choose_decision(
    profit: float,
    margin_pct: float,
    abc_class: str,
    *,
    financial_status: str,
    has_sales_activity: bool,
    revenue_attribution_zero: bool,
) -> tuple[str, str]:
    if financial_status in {"data_issue", "partial", "degraded"} or revenue_attribution_zero:
        return "watch", "DATA_ISSUE: verify financial attribution before economic decision"
    if profit == 0 and has_sales_activity:
        return "watch", "REVIEW: sales exist, but profit attribution is partial"
    if profit <= 0:
        return "liquidate", "LIQUIDATE: clear stock or stop ads"
    if profit > 0 and margin_pct >= 40 and abc_class == "A":
        return "scale", "SCALE: scale sales and ads"
    if profit > 0 and 20 <= margin_pct < 40:
        return "fix", "FIX: optimize price and ads"
    if 5 <= margin_pct < 20:
        return "watch", "WATCH: monitor and test"
    return "watch", "WATCH: monitor and test"


def _health_signal_ru(health_tier: str) -> str:
    tier = str(health_tier or "").strip().lower()
    if tier == "risk":
        return "Risk: SKU needs priority attention and stabilization."
    if tier == "unstable":
        return "Unstable: SKU needs stabilization of key metrics."
    if tier == "healthy":
        return "Healthy SKU: maintain control and targeted optimization."
    if tier == "strong":
        return "Strong SKU: has scaling potential."
    return ""


def _legacy_to_health_tier(status: str) -> str:
    key = str(status or "").strip().upper()
    if key == "LIQUIDATE":
        return "risk"
    if key == "WATCH":
        return "unstable"
    if key == "FIX":
        return "healthy"
    if key == "SCALE":
        return "strong"
    return ""


def build_decisions(
    metrics: Any,
    abc: Any,
    health: Any,
    territorial: Any | None = None,
    logistics: Any | None = None,
) -> Dict[str, Any]:
    sku_metrics = _extract_sku_metrics(metrics)
    abc_rows = _extract_abc(abc)
    health_items = _extract_health_items(health)
    territorial_items = _extract_territorial_items(territorial)
    logistics_items = _extract_logistics_items(logistics)
    funnel_by_sku = _extract_funnel_by_sku(metrics)
    funnel_summary = _extract_funnel_summary(metrics)
    profit_by_sku, profit_summary = _extract_profit_contribution(metrics)
    keyword_by_sku, keyword_summary = _extract_keyword_monitoring(metrics)

    abc_by_sku = {str(item.get("sku")): str(item.get("abc_class", "")) for item in abc_rows}
    health_by_sku = {str(item.get("sku")): item for item in health_items}

    summary: Dict[str, List[Dict[str, Any]]] = {
        "scale": [],
        "fix": [],
        "watch": [],
        "liquidate": [],
    }

    evaluated: List[Dict[str, Any]] = []
    for row in sku_metrics:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        profit = _as_float(row.get("profit"))
        margin_pct = _as_float(row.get("margin_pct") if row.get("margin_pct") is not None else row.get("margin"))
        abc_class = abc_by_sku.get(sku, "")
        health_row = health_by_sku.get(sku) or {}
        health_status = str(health_row.get("status") or "")
        health_tier = str(health_row.get("health_status") or "").strip().lower()
        if not health_tier:
            health_tier = _legacy_to_health_tier(health_status)
        health_factors = health_row.get("factors", [])
        if not isinstance(health_factors, list):
            health_factors = []
        health_signal_ru = _health_signal_ru(health_tier)
        territorial_row = territorial_items.get(sku) or {}
        territorial_status = str(territorial_row.get("status") or "")
        territorial_ktr = _as_float(territorial_row.get("ktr"))
        logistics_row = logistics_items.get(sku) or {}
        logistics_efficiency_status = str(logistics_row.get("logistics_efficiency_status") or "")
        priority_for_relocation = str(logistics_row.get("priority_for_relocation") or "none")
        locality_score = _as_float_or_none(logistics_row.get("locality_score"))
        row_financial_status = str(row.get("financial_status") or "ok").strip().lower()
        has_sales_activity = bool(row.get("has_sales_activity", False))
        revenue_attribution_zero = bool(row.get("revenue_attribution_zero", False))
        funnel_item = funnel_by_sku.get(sku, {})
        funnel_issue_type = str(funnel_item.get("issue_type") or "insufficient_data").strip() or "insufficient_data"
        funnel_issue_reason = str(
            funnel_item.get("issue_reason_ru")
            or FUNNEL_ISSUE_REASONS_RU.get(funnel_issue_type)
            or FUNNEL_ISSUE_REASONS_RU.get("insufficient_data", "")
        ).strip()
        profit_row = profit_by_sku.get(sku) or {}
        profit_group = str(profit_row.get("profit_group") or profit_row.get("class") or "").strip().upper()
        profit_share = _as_float_or_none(profit_row.get("profit_share"))
        profit_contribution_signal_ru = _profit_group_signal_ru(profit_group)
        keyword_row = keyword_by_sku.get(sku) or {}
        keyword_health_status = str(keyword_row.get("keyword_health_status") or "").strip().lower()
        keyword_query_count = int(keyword_row.get("query_count", 0) or 0)
        keyword_winner_count = int(keyword_row.get("winner_queries_count", 0) or 0)
        keyword_growth_count = int(keyword_row.get("growth_queries_count", 0) or 0)
        keyword_problem_count = int(keyword_row.get("weak_queries_count", 0) or 0) + int(
            keyword_row.get("costly_queries_count", 0) or 0
        )
        keyword_signals_ru = _keyword_signals_for_sku_ru(keyword_row)

        territorial_reasons: List[str] = []
        if territorial_ktr > 1.25:
            territorial_reasons = [
                "Stock is distributed across warehouses not according to demand",
                "There is a potential logistics gain from stock rebalancing",
            ]

        if logistics_efficiency_status == "critical":
            territorial_reasons.append("Critical logistics imbalance between demand and stock distribution.")
        elif logistics_efficiency_status == "inefficient":
            territorial_reasons.append("Logistics imbalance detected; consider stock rebalancing.")

        bucket, action = _choose_decision(
            profit,
            margin_pct,
            abc_class,
            financial_status=row_financial_status,
            has_sales_activity=has_sales_activity,
            revenue_attribution_zero=revenue_attribution_zero,
        )
        item = {
            "sku": sku,
            "action": action,
            "profit": round(profit, 2),
            "margin_pct": round(margin_pct, 2),
            "abc_class": abc_class,
            "health_status": health_status,
            "health_tier": health_tier or None,
            "health_factors": health_factors[:6],
            "health_signal_ru": health_signal_ru or None,
            "profit_group": profit_group or None,
            "profit_contribution_share": round(profit_share, 6) if profit_share is not None else None,
            "profit_signal_ru": profit_contribution_signal_ru or None,
            "keyword_health_status": keyword_health_status or None,
            "keyword_query_count": keyword_query_count,
            "keyword_winner_queries_count": keyword_winner_count,
            "keyword_growth_queries_count": keyword_growth_count,
            "keyword_problem_queries_count": keyword_problem_count,
            "keyword_signals_ru": keyword_signals_ru,
            "territorial_status": territorial_status,
            "territorial_ktr": round(territorial_ktr, 3) if territorial_ktr > 0 else None,
            "logistics_efficiency_status": logistics_efficiency_status or None,
            "priority_for_relocation": priority_for_relocation,
            "locality_score": round(locality_score, 3) if locality_score is not None else None,
            "territorial_reasons": territorial_reasons,
            "funnel_issue_type": funnel_issue_type,
            "funnel_issue_reason": funnel_issue_reason,
            "financial_status": row_financial_status,
            "has_sales_activity": has_sales_activity,
            "revenue_attribution_zero": revenue_attribution_zero,
            "decision_guard": "DATA_ISSUE" if row_financial_status in {"data_issue", "partial", "degraded"} or revenue_attribution_zero else "OK",
        }
        summary[bucket].append(item)
        evaluated.append(item)

    top_profit_skus = sorted(evaluated, key=lambda x: x["profit"], reverse=True)[:5]
    top_risk_skus = sorted(
        evaluated,
        key=lambda x: (
            0 if str(x.get("action") or "").strip().upper().startswith("LIQUIDATE") else 1,
            x["profit"],
            x["margin_pct"],
        ),
    )[:5]

    return {
        "summary": summary,
        "top_profit_skus": top_profit_skus,
        "top_risk_skus": top_risk_skus,
        "funnel_summary": funnel_summary if isinstance(funnel_summary, dict) else {},
        "funnel_issue_counts": (
            funnel_summary.get("issue_counts", {})
            if isinstance(funnel_summary, dict) and isinstance(funnel_summary.get("issue_counts"), dict)
            else {}
        ),
        "top_funnel_problem_skus": (
            funnel_summary.get("top_problem_skus", [])
            if isinstance(funnel_summary, dict) and isinstance(funnel_summary.get("top_problem_skus"), list)
            else []
        ),
        "profit_contribution_summary": profit_summary if isinstance(profit_summary, dict) else {},
        "profit_concentration_signal_ru": _profit_concentration_signal_ru(profit_summary),
        "keyword_summary": keyword_summary if isinstance(keyword_summary, dict) else {},
        "keyword_global_signal_ru": _keyword_global_signal_ru(keyword_summary),
    }
