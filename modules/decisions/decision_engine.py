"""Decision engine that combines ABC, profit and search insights."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


PRELIMINARY_MESSAGE = "Решения основаны на предварительных данных"


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _extract_queries(rows: list[Any], limit: int = 10) -> list[str]:
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or "").strip()
        if query:
            out.append(query)
        if len(out) >= limit:
            break
    return out


def _category_by_sku(abc_payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for category in ("A", "B", "C"):
        for item in _as_list(abc_payload.get(category)):
            if not isinstance(item, dict):
                continue
            sku = str(item.get("sku") or "").strip()
            if sku and sku not in out:
                out[sku] = category
    return out


def _decide_action(abc_category: str, profit: float | None) -> str:
    p = float(profit or 0.0)
    if abc_category == "A" and p > 0:
        return "scale"
    if abc_category == "B" and p > 0:
        return "optimize"
    if abc_category == "C" and p <= 0:
        return "remove_or_fix"
    if p > 0:
        return "optimize"
    return "remove_or_fix"


def _base_recommendations(abc_category: str, profit: float | None) -> list[str]:
    p = float(profit or 0.0)
    if abc_category == "A" and p > 0:
        return [
            "Увеличивать рекламу",
            "Усиливать SEO",
            "Следить за остатками",
        ]
    if abc_category == "B" and p > 0:
        return [
            "Дорабатывать карточку",
            "Работать с конверсией",
            "Тестировать рекламу",
        ]
    if abc_category == "C" and p <= 0:
        return [
            "Отключить рекламу",
            "Проверить спрос",
            "Рассмотреть вывод из ассортимента",
        ]
    if p > 0:
        return ["Продолжать оптимизацию SKU"]
    return ["Проверить экономику SKU и спрос"]


def build_sku_decisions(
    *,
    abc_payload: dict[str, Any],
    sku_profit_payload: dict[str, Any],
    search_insights_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build sku_decisions payload from ABC + profit + search insights."""
    abc = abc_payload if isinstance(abc_payload, dict) else {}
    sku_profit = sku_profit_payload if isinstance(sku_profit_payload, dict) else {}
    search_insights = search_insights_payload if isinstance(search_insights_payload, dict) else {}

    abc_status = str(abc.get("abc_status") or "preliminary")
    decision_status = "preliminary" if abc_status == "preliminary" else "final"

    profitable_queries = _extract_queries(_as_list(search_insights.get("profitable_queries")))
    wasted_traffic = _extract_queries(_as_list(search_insights.get("wasted_traffic")))
    low_visibility = _extract_queries(_as_list(search_insights.get("low_visibility_high_demand")))

    category_map = _category_by_sku(abc)
    profit_items = _as_list(sku_profit.get("items"))
    if not profit_items:
        payload = {
            "status": "ok",
            "decision_status": decision_status,
            "items": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "decision_module",
        }
        if decision_status == "preliminary":
            payload["message"] = PRELIMINARY_MESSAGE
        return payload

    items: list[dict[str, Any]] = []
    for row in profit_items:
        if not isinstance(row, dict):
            continue

        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        profit = _to_float(row.get("profit"))
        margin_pct = _to_float(row.get("margin_pct"))
        drr_ads = _to_float(row.get("drr_ads"))
        drr_total = _to_float(row.get("drr_total"))
        abc_category = str(category_map.get(sku) or "C")

        action = _decide_action(abc_category, profit)
        recommendations = _base_recommendations(abc_category, profit)

        if drr_ads is not None and drr_ads > 40:
            recommendations.append("Реклама неэффективна — высокий DRR")
        if drr_total is not None and drr_total > 20:
            recommendations.append("SKU сильно зависит от рекламы")
        if wasted_traffic:
            recommendations.append("Отключить нерелевантные запросы")
        if low_visibility:
            recommendations.append("Усилить SEO/рекламу по этим запросам")

        # De-duplicate recommendations preserving order.
        dedup: list[str] = []
        seen = set()
        for rec in recommendations:
            rec_s = str(rec).strip()
            if not rec_s or rec_s in seen:
                continue
            seen.add(rec_s)
            dedup.append(rec_s)

        items.append(
            {
                "sku": sku,
                "abc_category": abc_category,
                "profit": round(float(profit), 2) if profit is not None else None,
                "margin_pct": round(float(margin_pct), 2) if margin_pct is not None else None,
                "drr_ads": round(float(drr_ads), 2) if drr_ads is not None else None,
                "drr_total": round(float(drr_total), 2) if drr_total is not None else None,
                "action": action,
                "recommendations": dedup,
                "related_keywords": {
                    "profitable_queries": profitable_queries[:5],
                    "wasted_traffic": wasted_traffic[:5],
                    "low_visibility_high_demand": low_visibility[:5],
                },
            }
        )

    payload = {
        "status": "ok",
        "decision_status": decision_status,
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "decision_module",
    }
    if decision_status == "preliminary":
        payload["message"] = PRELIMINARY_MESSAGE
    return payload

