from __future__ import annotations

from typing import Any, Dict, List, Mapping

from .query_utils import merge_thresholds, to_float_or_none

DEFAULT_QUERY_THRESHOLDS: Dict[str, float] = {
    "min_impressions_for_analysis": 120.0,
    "winner_min_impressions": 400.0,
    "min_clicks_for_analysis": 12.0,
    "winner_min_conversion": 0.02,
    "winner_min_click_to_order": 0.08,
    "growth_max_impressions": 250.0,
    "growth_min_conversion": 0.02,
    "low_conversion_max": 0.006,
    "low_relevance_min_clicks": 25.0,
    "low_relevance_max_click_to_order": 0.02,
    "traffic_only_min_impressions": 250.0,
    "traffic_only_max_cart_rate": 0.01,
    "costly_min_spend": 500.0,
    "costly_max_orders": 1.0,
    "costly_min_spend_per_order": 700.0,
}

QUERY_STATUS_REASONS_RU: Dict[str, str] = {
    "winner": "Сильный запрос: дает устойчивый коммерческий результат.",
    "growth_opportunity": "Перспективный запрос: есть конверсия, но мало показов.",
    "low_conversion": "Низкая конверсия: трафик есть, заказы слабые.",
    "low_relevance": "Низкая релевантность: пользователи кликают, но не покупают.",
    "traffic_only": "Трафик без коммерции: показы есть, действий по покупке почти нет.",
    "no_orders": "Нет заказов: запрос дает показы/клики без заказов.",
    "costly": "Дорогой запрос: расходы не подтверждаются заказами.",
    "insufficient_data": "Недостаточно данных по запросу для диагностики.",
}

QUERY_STATUSES: tuple[str, ...] = (
    "winner",
    "growth_opportunity",
    "low_conversion",
    "low_relevance",
    "traffic_only",
    "no_orders",
    "costly",
    "insufficient_data",
)


def classify_query_item(item: Mapping[str, Any], thresholds: Mapping[str, Any] | None = None) -> str:
    cfg = merge_thresholds(DEFAULT_QUERY_THRESHOLDS, thresholds)

    impressions = to_float_or_none(item.get("impressions"))
    clicks = to_float_or_none(item.get("clicks"))
    orders = to_float_or_none(item.get("orders"))
    spend = to_float_or_none(item.get("spend"))
    conversion = to_float_or_none(item.get("conversion"))
    click_to_order = to_float_or_none(item.get("click_to_order"))
    cart_rate = to_float_or_none(item.get("cart_rate"))
    spend_per_order = to_float_or_none(item.get("spend_per_order"))

    has_signal = any(value is not None and value > 0 for value in (impressions, clicks, orders, spend))
    if not has_signal:
        return "insufficient_data"

    if spend is not None and spend >= cfg["costly_min_spend"]:
        if (orders is None or orders <= cfg["costly_max_orders"]) or (
            spend_per_order is not None and spend_per_order >= cfg["costly_min_spend_per_order"]
        ):
            return "costly"

    if (
        impressions is not None
        and impressions >= cfg["winner_min_impressions"]
        and orders is not None
        and orders > 0
        and conversion is not None
        and conversion >= cfg["winner_min_conversion"]
        and (click_to_order is None or click_to_order >= cfg["winner_min_click_to_order"])
    ):
        return "winner"

    if (
        impressions is not None
        and impressions > 0
        and impressions <= cfg["growth_max_impressions"]
        and orders is not None
        and orders > 0
        and conversion is not None
        and conversion >= cfg["growth_min_conversion"]
    ):
        return "growth_opportunity"

    if (
        impressions is not None
        and impressions >= cfg["traffic_only_min_impressions"]
        and (cart_rate is None or cart_rate <= cfg["traffic_only_max_cart_rate"])
        and (orders is None or orders <= 0)
    ):
        return "traffic_only"

    if (
        ((impressions is not None and impressions >= cfg["min_impressions_for_analysis"]) or (clicks is not None and clicks >= cfg["min_clicks_for_analysis"]))
        and (orders is None or orders <= 0)
    ):
        return "no_orders"

    if (
        clicks is not None
        and clicks >= cfg["low_relevance_min_clicks"]
        and (click_to_order is None or click_to_order <= cfg["low_relevance_max_click_to_order"])
    ):
        return "low_relevance"

    if (
        impressions is not None
        and impressions >= cfg["winner_min_impressions"]
        and conversion is not None
        and conversion <= cfg["low_conversion_max"]
    ):
        return "low_conversion"

    return "insufficient_data"


def classify_query_items(
    items: List[Dict[str, Any]],
    thresholds: Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = classify_query_item(item, thresholds=thresholds)
        row = dict(item)
        row["query_status"] = status
        row["query_reason_ru"] = QUERY_STATUS_REASONS_RU.get(status, QUERY_STATUS_REASONS_RU["insufficient_data"])
        out.append(row)
    return out



