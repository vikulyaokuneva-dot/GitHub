"""Presentation layer for PDF payloads.

Input: FactsBundle (already calculated metrics/facts).
Output: human-readable Russian view-model fragments for PDF builder.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import FactItem, FactsBundle


def _find_fact_item(facts: FactsBundle, section_name: str, key: str) -> FactItem | None:
    section = facts.sections.get(section_name)
    if section is None:
        return None
    for item in section.items:
        if item.key == key:
            return item
    return None


def _metric_value_and_status(facts: FactsBundle, section_name: str, key: str) -> tuple[Any, str]:
    item = _find_fact_item(facts, section_name, key)
    if item is None:
        return None, "unavailable"
    return item.value.value, str(item.value.status or "unavailable")


def _is_estimated_financial_mode(facts: FactsBundle) -> bool:
    section = facts.sections.get("financial")
    diagnostics = section.diagnostics if section is not None and isinstance(section.diagnostics, dict) else {}
    model_mode = str(diagnostics.get("financial_model_mode") or diagnostics.get("financial_mode") or "")
    estimate_used = bool(diagnostics.get("profitability_estimate_used", False))
    return model_mode == "estimated" or estimate_used


def _status_for_row(metric_status: str, value: Any) -> str:
    if value is None or str(metric_status).strip().lower() == "unavailable":
        return "unavailable"
    return "confirmed"


def _format_number(value: float, *, decimals: int = 0) -> str:
    if decimals <= 0:
        return f"{int(round(value)):,}".replace(",", " ")
    formatted = f"{value:,.{decimals}f}".replace(",", " ")
    return formatted


def _append_quality_suffix(text: str, *, metric_status: str, estimated: bool) -> str:
    if text == "нет данных":
        return text
    if estimated:
        return text
    if str(metric_status).strip().lower() == "partial":
        return f"{text} (частично)"
    return text


def _format_count(value: Any, *, metric_status: str, estimated: bool = False) -> str:
    if value is None:
        return "нет данных"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric - round(numeric)) < 1e-9:
        base = _format_number(float(round(numeric)), decimals=0)
    else:
        base = _format_number(numeric, decimals=2)
    return _append_quality_suffix(base, metric_status=metric_status, estimated=estimated)


def format_money(value: Any, status: str | None = None) -> str:
    if value is None:
        return "нет данных"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "нет данных"

    if abs(numeric - round(numeric)) < 1e-9:
        base = f"{_format_number(numeric, decimals=0)} ₽"
    else:
        base = f"{_format_number(numeric, decimals=2)} ₽"

    if str(status or "").strip().lower() == "estimated":
        return f"{base} (оценка)"
    return base


def format_percent(value: Any, status: str | None = None) -> str:
    if value is None:
        return "нет данных"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "нет данных"

    if -1.0 <= numeric <= 1.0:
        numeric = numeric * 100.0
    base = f"{numeric:.2f}%"
    if str(status or "").strip().lower() == "estimated":
        return f"{base} (оценка)"
    return base


def build_kpi_cards(facts: FactsBundle) -> list[dict[str, Any]]:
    estimated_financial = _is_estimated_financial_mode(facts)

    payout_value, payout_status = _metric_value_and_status(facts, "financial", "seller_payout")
    profit_value, profit_status = _metric_value_and_status(facts, "financial", "net_profit_like")
    ads_spend_value, ads_spend_status = _metric_value_and_status(facts, "ads", "spend")
    orders_value, orders_status = _metric_value_and_status(facts, "daily", "orders_count")
    if orders_value is None:
        orders_value, orders_status = _metric_value_and_status(facts, "financial", "orders_count")

    profit_mode = "estimated" if estimated_financial else None

    return [
        {
            "label": "К перечислению продавцу",
            "value": _append_quality_suffix(
                format_money(payout_value),
                metric_status=payout_status,
                estimated=False,
            ),
            "status": _status_for_row(payout_status, payout_value),
        },
        {
            "label": "Чистая прибыль",
            "value": _append_quality_suffix(
                format_money(profit_value, status=profit_mode),
                metric_status=profit_status,
                estimated=profit_mode == "estimated",
            ),
            "status": _status_for_row(profit_status, profit_value),
        },
        {
            "label": "Расход на рекламу",
            "value": _append_quality_suffix(
                format_money(ads_spend_value),
                metric_status=ads_spend_status,
                estimated=False,
            ),
            "status": _status_for_row(ads_spend_status, ads_spend_value),
        },
        {
            "label": "Заказы",
            "value": _format_count(orders_value, metric_status=orders_status, estimated=False),
            "status": _status_for_row(orders_status, orders_value),
        },
    ]


def map_finance_section(facts: FactsBundle) -> list[dict[str, Any]]:
    estimated_financial = _is_estimated_financial_mode(facts)
    estimated_status = "estimated" if estimated_financial else None

    key_map = [
        ("Валовая выручка", "revenue_gross", "money"),
        ("К перечислению продавцу", "seller_payout", "money"),
        ("Комиссия WB", "commission_amount", "money"),
        ("Логистика", "logistics_cost", "money"),
        ("Хранение", "storage_cost", "money"),
        ("Штрафы", "penalties_amount", "money"),
        ("Себестоимость", None, "money"),
        ("Налоги", None, "money"),
        ("Чистая прибыль", "net_profit_like", "money"),
        ("Маржа", "margin", "percent"),
    ]

    rows: list[dict[str, Any]] = []
    for label, key, kind in key_map:
        if key is None:
            value = "нет данных"
            status = "unavailable"
            row_status = "unavailable"
        else:
            raw_value, metric_status = _metric_value_and_status(facts, "financial", key)
            mode_status = estimated_status if key in {"net_profit_like", "margin"} else None
            if kind == "percent":
                value = format_percent(raw_value, status=mode_status)
            else:
                value = format_money(raw_value, status=mode_status)
            value = _append_quality_suffix(
                value,
                metric_status=metric_status,
                estimated=mode_status == "estimated",
            )
            status = metric_status
            row_status = _status_for_row(metric_status, raw_value)

        rows.append({"label": label, "value": value, "status": row_status, "metric_status": status})
    return rows


def map_funnel_section(facts: FactsBundle) -> list[dict[str, Any]]:
    key_map = [
        ("Просмотры", "impressions"),
        ("Добавления в корзину", "cart_adds"),
        ("Заказы", "orders"),
        ("Выкупы", "buys"),
    ]
    rows: list[dict[str, Any]] = []
    for label, key in key_map:
        raw_value, metric_status = _metric_value_and_status(facts, "funnel", key)
        rows.append(
            {
                "label": label,
                "value": _format_count(raw_value, metric_status=metric_status, estimated=False),
                "status": _status_for_row(metric_status, raw_value),
                "metric_status": metric_status,
            }
        )
    return rows


def map_ads_section(facts: FactsBundle) -> dict[str, Any]:
    key_map = [
        ("Расход на рекламу", "spend", "money"),
        ("Клики", "clicks", "count"),
        ("CTR", "ctr", "percent"),
        ("Заказы из рекламы", "orders", "count"),
        ("Выручка из рекламы", "revenue", "money"),
    ]

    rows: list[dict[str, Any]] = []
    has_any_data = False
    for label, key, kind in key_map:
        raw_value, metric_status = _metric_value_and_status(facts, "ads", key)
        if kind == "money":
            value = format_money(raw_value)
        elif kind == "percent":
            value = format_percent(raw_value)
        else:
            value = _format_count(raw_value, metric_status=metric_status, estimated=False)
        value = _append_quality_suffix(value, metric_status=metric_status, estimated=False)
        if raw_value is not None:
            has_any_data = True
        rows.append(
            {
                "label": label,
                "value": value,
                "status": _status_for_row(metric_status, raw_value),
                "metric_status": metric_status,
            }
        )

    if has_any_data:
        return {"has_data": True, "rows": rows, "message": None}

    source_reason_map = facts.diagnostics.get("source_reason_map")
    reason_map = dict(source_reason_map) if isinstance(source_reason_map, dict) else {}
    reason = str(reason_map.get("ads") or reason_map.get("ads_stats") or reason_map.get("ads_campaigns") or "").strip()
    reason_text_map = {
        "request_failed": "API не вернул данные",
        "auth_failed": "ошибка авторизации API",
        "empty_payload": "API вернул пустой ответ",
        "ok_empty_payload": "API вернул пустой ответ",
        "parse_failed": "ответ API не удалось разобрать",
        "source_missing": "источник недоступен",
        "no_data_for_date": "за выбранную дату данных нет",
    }
    reason_ru = reason_text_map.get(reason.lower(), reason)
    if reason_ru:
        message = f"Данные по рекламе отсутствуют ({reason_ru})"
    else:
        message = "Данные по рекламе отсутствуют"
    return {"has_data": False, "rows": [], "message": message}


def map_stock_section(facts: FactsBundle) -> list[dict[str, Any]]:
    total_value, total_status = _metric_value_and_status(facts, "stock", "total_stock_units")
    in_stock_value, in_stock_status = _metric_value_and_status(facts, "stock", "in_stock_items_count")
    out_stock_value, out_stock_status = _metric_value_and_status(facts, "stock", "out_of_stock_items_count")

    total_text = _format_count(total_value, metric_status=total_status, estimated=False)

    coverage = "нет данных"
    if in_stock_value is not None and out_stock_value is not None:
        try:
            in_stock = int(float(in_stock_value))
            out_stock = int(float(out_stock_value))
            total_entities = in_stock + out_stock
            coverage = f"{in_stock} SKU в наличии из {total_entities}"
        except (TypeError, ValueError):
            coverage = "нет данных"

    deficit_risk = "нет данных"
    if out_stock_value is not None:
        try:
            out_stock = float(out_stock_value)
            deficit_risk = "есть риск дефицита" if out_stock > 0 else "риск дефицита низкий"
        except (TypeError, ValueError):
            deficit_risk = "нет данных"

    return [
        {
            "label": "Остаток",
            "value": total_text,
            "status": _status_for_row(total_status, total_value),
        },
        {
            "label": "Покрытие",
            "value": coverage,
            "status": "confirmed" if coverage != "нет данных" else "unavailable",
        },
        {
            "label": "Риск дефицита",
            "value": deficit_risk,
            "status": "confirmed" if deficit_risk != "нет данных" else "unavailable",
        },
    ]


def map_health_section(facts: FactsBundle) -> list[dict[str, Any]]:
    key_map = [
        ("Оценка здоровья бизнеса", "business_health_score", "count"),
        ("Статус оценки", "score_status", "text"),
        ("Сигналы риска SKU", "sku_health_signals_count", "count"),
        ("Проблемные SKU", "problematic_sku_count", "count"),
        ("Риск неликвида", "dead_stock_risk_count", "count"),
        ("Риск оверстока", "overstock_risk_count", "count"),
        ("Комментарий к статусу", "business_health_status_note", "text"),
    ]
    rows: list[dict[str, Any]] = []
    for label, key, kind in key_map:
        value, metric_status = _metric_value_and_status(facts, "health", key)
        if kind == "count":
            text = _format_count(value, metric_status=metric_status, estimated=False)
        else:
            text = "нет данных" if value in (None, "") else str(value)
        rows.append(
            {
                "label": label,
                "value": text,
                "status": _status_for_row(metric_status, value),
                "metric_status": metric_status,
            }
        )
    return rows


__all__ = [
    "build_kpi_cards",
    "format_money",
    "format_percent",
    "map_ads_section",
    "map_finance_section",
    "map_funnel_section",
    "map_health_section",
    "map_stock_section",
]

