from __future__ import annotations

from typing import Any, Dict, List


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def _choose_decision(profit: float, margin_pct: float, abc_class: str) -> tuple[str, str]:
    if profit <= 0:
        return "liquidate", "Ликвидировать остатки или отключить рекламу"
    if profit > 0 and margin_pct >= 40 and abc_class == "A":
        return "scale", "Масштабировать продажи и рекламу"
    if profit > 0 and 20 <= margin_pct < 40:
        return "fix", "Оптимизировать цену и рекламу"
    if 5 <= margin_pct < 20:
        return "watch", "Наблюдать и тестировать"
    return "watch", "Наблюдать и тестировать"


def build_decisions(metrics: Any, abc: Any, health: Any, territorial: Any | None = None) -> Dict[str, Any]:
    sku_metrics = _extract_sku_metrics(metrics)
    abc_rows = _extract_abc(abc)
    health_items = _extract_health_items(health)
    territorial_items = _extract_territorial_items(territorial)

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
        territorial_reasons: List[str] = []
        if territorial_ktr > 1.25:
            territorial_reasons = [
                "Товар распределен по складам не в соответствии со спросом",
                "Есть потенциал снижения логистики через перераспределение остатков",
            ]

        bucket, action = _choose_decision(profit, margin_pct, abc_class)
        item = {
            "sku": sku,
            "action": action,
            "profit": round(profit, 2),
            "margin_pct": round(margin_pct, 2),
            "abc_class": abc_class,
            "health_status": health_status,
            "territorial_status": territorial_status,
            "territorial_ktr": round(territorial_ktr, 3) if territorial_ktr > 0 else None,
            "territorial_reasons": territorial_reasons,
        }
        summary[bucket].append(item)
        evaluated.append(item)

    top_profit_skus = sorted(evaluated, key=lambda x: x["profit"], reverse=True)[:5]
    top_risk_skus = sorted(
        evaluated,
        key=lambda x: (
            0 if x["action"].startswith("Ликвидировать") else 1,
            x["profit"],
            x["margin_pct"],
        ),
    )[:5]

    return {
        "summary": summary,
        "top_profit_skus": top_profit_skus,
        "top_risk_skus": top_risk_skus,
    }
