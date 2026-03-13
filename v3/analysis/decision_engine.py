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
        return "watch", "DATA_ISSUE: проверить финансовую атрибуцию перед экономическим решением"
    if profit == 0 and has_sales_activity:
        return "watch", "REVIEW: есть продажи, но атрибуция прибыли неполная"
    if profit <= 0:
        return "liquidate", "LIQUIDATE: ликвидировать остатки или отключить рекламу"
    if profit > 0 and margin_pct >= 40 and abc_class == "A":
        return "scale", "SCALE: масштабировать продажи и рекламу"
    if profit > 0 and 20 <= margin_pct < 40:
        return "fix", "FIX: оптимизировать цену и рекламу"
    if 5 <= margin_pct < 20:
        return "watch", "WATCH: наблюдать и тестировать"
    return "watch", "WATCH: наблюдать и тестировать"


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
        health_status = str((health_by_sku.get(sku) or {}).get("status", ""))
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

        territorial_reasons: List[str] = []
        if territorial_ktr > 1.25:
            territorial_reasons = [
                "Товар распределен по складам не в соответствии со спросом",
                "Есть потенциал снижения логистики через перераспределение остатков",
            ]

        if logistics_efficiency_status == "critical":
            territorial_reasons.append("Критичный логистический дисбаланс между спросом и распределением остатков.")
        elif logistics_efficiency_status == "inefficient":
            territorial_reasons.append("Обнаружен логистический дисбаланс; стоит рассмотреть перераспределение остатков.")

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
    }
