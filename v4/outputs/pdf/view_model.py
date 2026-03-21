"""Presentation layer for PDF payloads.

Input: FactsBundle (already calculated metrics/facts).
Output: human-readable Russian view-model fragments for PDF builder.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import FactItem, FactsBundle


_FINANCIAL_STATUSES = {"confirmed", "partial", "unavailable"}

_REASON_MAP = {
    "missing dependencies": "не хватает обязательных компонентов",
    "missing profit or revenue": "не хватает прибыли или базы выручки",
    "revenue must be positive": "выручка должна быть больше нуля",
    "without realization components": "нет данных финальной реализации",
    "is unavailable": "источник не предоставил значение",
    "insufficient": "недостаточно данных для расчета",
    "partial": "данные частично заполнены",
    "cogs not provided": "себестоимость не входит в текущий контур V4",
    "tax not provided": "налог не входит в текущий контур V4",
}


def _find_fact_item(facts: FactsBundle, section_name: str, key: str) -> FactItem | None:
    section = facts.sections.get(section_name)
    if section is None:
        return None
    for item in section.items:
        if item.key == key:
            return item
    return None


def _sanitize_note(*, value: Any, note: str | None) -> str | None:
    text = str(note or "").strip()
    if not text:
        return None
    if value is not None and "unavailable" in text.lower():
        return None
    return text


def _metric_payload(facts: FactsBundle, section_name: str, key: str) -> dict[str, Any]:
    item = _find_fact_item(facts, section_name, key)
    if item is None:
        return {"value": None, "status": "unavailable", "note": None, "item": None}

    metric_status = str(item.value.status or "unavailable").strip().lower()
    if metric_status not in _FINANCIAL_STATUSES:
        metric_status = "unavailable"
    metric_note = _sanitize_note(value=item.value.value, note=item.value.note)
    return {
        "value": item.value.value,
        "status": metric_status,
        "note": metric_note,
        "item": item,
    }


def _is_estimated_financial_mode(facts: FactsBundle) -> bool:
    section = facts.sections.get("financial")
    diagnostics = section.diagnostics if section is not None and isinstance(section.diagnostics, dict) else {}
    model_mode = str(diagnostics.get("financial_model_mode") or diagnostics.get("financial_mode") or "")
    estimate_used = bool(diagnostics.get("profitability_estimate_used", False))
    return model_mode == "estimated" or estimate_used


def _format_number(value: float, *, decimals: int = 0) -> str:
    if decimals <= 0:
        return f"{int(round(value)):,}".replace(",", " ")
    return f"{value:,.{decimals}f}".replace(",", " ")


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


def _format_count(value: Any) -> str:
    if value is None:
        return "нет данных"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric - round(numeric)) < 1e-9:
        return _format_number(numeric, decimals=0)
    return _format_number(numeric, decimals=2)


def _humanize_reason(note: str | None) -> str | None:
    text = str(note or "").strip()
    if not text:
        return None
    lowered = text.lower()
    for key, reason in _REASON_MAP.items():
        if key in lowered:
            return reason
    return text


def _decorate_value(base_text: str, *, metric_status: str, estimated: bool) -> str:
    if base_text == "нет данных":
        return base_text
    suffixes: list[str] = []
    if estimated:
        suffixes.append("оценка")
    if metric_status == "partial":
        suffixes.append("частично")
    if suffixes:
        return f"{base_text} ({', '.join(suffixes)})"
    return base_text


def _missing_text(reason: str | None) -> str:
    if not reason:
        return "нет данных"
    return f"нет данных ({reason})"


def _row_status(metric_status: str, value: Any) -> str:
    status = str(metric_status or "unavailable").strip().lower()
    if status not in _FINANCIAL_STATUSES:
        status = "unavailable"
    if value is None and status == "confirmed":
        return "unavailable"
    return status


def _build_row(
    *,
    label: str,
    kind: str,
    metric: dict[str, Any],
    estimated: bool = False,
    default_missing_reason: str | None = None,
    force_note: str | None = None,
) -> dict[str, Any]:
    value = metric.get("value")
    metric_status = str(metric.get("status") or "unavailable").strip().lower()
    metric_note = force_note if force_note is not None else metric.get("note")
    reason = _humanize_reason(metric_note) or default_missing_reason

    if value is None:
        value_text = _missing_text(reason)
    elif kind == "money":
        value_text = _decorate_value(
            format_money(value, status=("estimated" if estimated else None)),
            metric_status=metric_status,
            estimated=False,
        )
    elif kind == "percent":
        value_text = _decorate_value(
            format_percent(value, status=("estimated" if estimated else None)),
            metric_status=metric_status,
            estimated=False,
        )
    else:
        value_text = _decorate_value(_format_count(value), metric_status=metric_status, estimated=estimated)

    return {
        "label": label,
        "value": value_text,
        "status": _row_status(metric_status, value),
        "note": metric_note,
        "reason": reason,
    }


def build_kpi_cards(facts: FactsBundle) -> list[dict[str, Any]]:
    estimated_financial = _is_estimated_financial_mode(facts)

    payout = _metric_payload(facts, "financial", "seller_payout")
    profit = _metric_payload(facts, "financial", "net_profit_like")
    ads_spend = _metric_payload(facts, "ads", "spend")
    orders = _metric_payload(facts, "daily", "orders_count")
    if orders["value"] is None:
        orders = _metric_payload(facts, "financial", "orders_count")

    return [
        _build_row(
            label="К перечислению продавцу",
            kind="money",
            metric=payout,
            default_missing_reason="нет данных о перечислении продавцу",
        ),
        _build_row(
            label="Чистая прибыль",
            kind="money",
            metric=profit,
            estimated=estimated_financial,
            default_missing_reason="не удалось рассчитать прибыль",
        ),
        _build_row(
            label="Расход на рекламу",
            kind="money",
            metric=ads_spend,
            default_missing_reason="данные по рекламе отсутствуют",
        ),
        _build_row(
            label="Заказы",
            kind="count",
            metric=orders,
            default_missing_reason="нет данных по заказам",
        ),
    ]


def _profit_component_check(facts: FactsBundle) -> dict[str, Any]:
    estimated_financial = _is_estimated_financial_mode(facts)
    revenue = _metric_payload(facts, "financial", "revenue_gross")
    cost_keys = [
        "commission_amount",
        "acquiring_amount",
        "pvz_amount",
        "logistics_cost",
        "storage_cost",
        "penalties_amount",
        "deductions_amount",
        "acceptance_amount",
        "paid_acceptance_amount",
        "other_costs_amount",
    ]
    costs = {key: _metric_payload(facts, "financial", key) for key in cost_keys}
    if revenue["value"] is None:
        return {
            "value": None,
            "status": "unavailable",
            "note": "missing dependencies: ['revenue_gross']",
            "estimated": estimated_financial,
            "missing": ["revenue_gross"],
        }

    available_sum = 0.0
    available_any = False
    missing: list[str] = []
    partial_any = revenue["status"] == "partial"
    for key, payload in costs.items():
        if payload["value"] is None:
            missing.append(key)
            continue
        available_any = True
        available_sum += float(payload["value"])
        if payload["status"] == "partial":
            partial_any = True

    if not available_any:
        return {
            "value": None,
            "status": "unavailable",
            "note": "insufficient data for component profit check",
            "estimated": estimated_financial,
            "missing": list(costs.keys()),
        }

    computed = float(revenue["value"]) - available_sum
    status = "confirmed"
    if partial_any or missing or estimated_financial:
        status = "partial"
    note = None
    if missing:
        note = f"missing components: {sorted(missing)}"
    return {
        "value": computed,
        "status": status,
        "note": note,
        "estimated": estimated_financial,
        "missing": sorted(missing),
    }


def _profit_delta(facts: FactsBundle, component_check: dict[str, Any]) -> dict[str, Any]:
    estimated_financial = _is_estimated_financial_mode(facts)
    reported_profit = _metric_payload(facts, "financial", "net_profit_like")
    if reported_profit["value"] is None or component_check.get("value") is None:
        missing: list[str] = []
        if reported_profit["value"] is None:
            missing.append("net_profit_like")
        if component_check.get("value") is None:
            missing.append("component_profit_check")
        return {
            "value": None,
            "status": "unavailable",
            "note": f"missing dependencies: {missing}",
            "estimated": estimated_financial,
        }
    delta = float(reported_profit["value"]) - float(component_check["value"])
    if abs(delta) < 1e-9:
        delta = 0.0
    status = "confirmed"
    if (
        reported_profit["status"] == "partial"
        or str(component_check.get("status")) == "partial"
        or estimated_financial
    ):
        status = "partial"
    return {
        "value": delta,
        "status": status,
        "note": None,
        "estimated": estimated_financial,
    }


def map_finance_section(facts: FactsBundle) -> list[dict[str, Any]]:
    estimated_financial = _is_estimated_financial_mode(facts)
    financial = {
        key: _metric_payload(facts, "financial", key)
        for key in (
            "revenue_gross",
            "sales_amount",
            "seller_payout",
            "commission_amount",
            "acquiring_amount",
            "pvz_amount",
            "logistics_cost",
            "storage_cost",
            "penalties_amount",
            "deductions_amount",
            "acceptance_amount",
            "paid_acceptance_amount",
            "other_costs_amount",
            "net_profit_like",
            "margin",
        )
    }
    ads_spend = _metric_payload(facts, "ads", "spend")

    rows: list[dict[str, Any]] = []
    rows.append(
        _build_row(
            label="Валовая выручка",
            kind="money",
            metric=financial["revenue_gross"],
            default_missing_reason="нет данных по валовой выручке",
        )
    )
    rows.append(
        _build_row(
            label="WB реализовал",
            kind="money",
            metric=financial["sales_amount"],
            default_missing_reason="нет данных по реализованной выручке",
        )
    )
    rows.append(
        _build_row(
            label="К перечислению продавцу",
            kind="money",
            metric=financial["seller_payout"],
            default_missing_reason="нет данных о перечислении продавцу",
        )
    )
    rows.append(_build_row(label="Комиссия WB", kind="money", metric=financial["commission_amount"], default_missing_reason="нет данных по комиссии WB"))
    rows.append(_build_row(label="Эквайринг", kind="money", metric=financial["acquiring_amount"], default_missing_reason="нет данных по эквайрингу"))
    rows.append(_build_row(label="ПВЗ / выдача-возврат", kind="money", metric=financial["pvz_amount"], default_missing_reason="нет данных по ПВЗ/выдаче-возврату"))
    rows.append(_build_row(label="Логистика", kind="money", metric=financial["logistics_cost"], default_missing_reason="нет данных по логистике"))
    rows.append(_build_row(label="Хранение", kind="money", metric=financial["storage_cost"], default_missing_reason="нет данных по хранению"))
    rows.append(_build_row(label="Штрафы", kind="money", metric=financial["penalties_amount"], default_missing_reason="нет данных по штрафам"))
    rows.append(_build_row(label="Удержания", kind="money", metric=financial["deductions_amount"], default_missing_reason="нет данных по удержаниям"))

    loyalty_value = None
    loyalty_status = "unavailable"
    if financial["acceptance_amount"]["value"] is not None or financial["paid_acceptance_amount"]["value"] is not None:
        loyalty_value = float(financial["acceptance_amount"]["value"] or 0.0) + float(financial["paid_acceptance_amount"]["value"] or 0.0)
        loyalty_status = "partial"
    rows.append(
        _build_row(
            label="Лояльность / бонусные удержания",
            kind="money",
            metric={"value": loyalty_value, "status": loyalty_status, "note": "детализация бонусных удержаний в источнике ограничена"},
            default_missing_reason="детализация бонусных удержаний недоступна",
        )
    )
    rows.append(_build_row(label="Прочие корректировки", kind="money", metric=financial["other_costs_amount"], default_missing_reason="нет данных по прочим корректировкам"))

    rows.append(
        _build_row(
            label="Себестоимость",
            kind="money",
            metric={"value": None, "status": "unavailable", "note": "COGS not provided by current financial contour"},
            default_missing_reason="себестоимость не входит в текущий контур V4",
        )
    )
    rows.append(
        _build_row(
            label="Налог",
            kind="money",
            metric={"value": None, "status": "unavailable", "note": "tax not provided by current financial contour"},
            default_missing_reason="налог не входит в текущий контур V4",
        )
    )
    rows.append(
        _build_row(
            label="Расход на рекламу",
            kind="money",
            metric=ads_spend,
            default_missing_reason="данные по рекламе отсутствуют",
        )
    )
    rows.append(
        _build_row(
            label="Чистая прибыль",
            kind="money",
            metric=financial["net_profit_like"],
            estimated=estimated_financial,
            default_missing_reason="не удалось рассчитать чистую прибыль",
        )
    )
    rows.append(
        _build_row(
            label="Маржа",
            kind="percent",
            metric=financial["margin"],
            estimated=estimated_financial,
            default_missing_reason="не удалось рассчитать маржу",
        )
    )

    component_check = _profit_component_check(facts)
    rows.append(
        _build_row(
            label="Проверка прибыли по компонентам",
            kind="money",
            metric={"value": component_check["value"], "status": component_check["status"], "note": component_check.get("note")},
            estimated=bool(component_check.get("estimated")),
            default_missing_reason="не удалось собрать компонентную проверку прибыли",
        )
    )

    delta = _profit_delta(facts, component_check)
    rows.append(
        _build_row(
            label="Дельта расчета прибыли",
            kind="money",
            metric={"value": delta["value"], "status": delta["status"], "note": delta.get("note")},
            estimated=bool(delta.get("estimated")),
            default_missing_reason="невозможно сравнить расчетную и отчетную прибыль",
        )
    )

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
        payload = _metric_payload(facts, "funnel", key)
        rows.append(
            _build_row(
                label=label,
                kind="count",
                metric=payload,
                default_missing_reason="данные воронки отсутствуют",
            )
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
        payload = _metric_payload(facts, "ads", key)
        if payload["value"] is not None:
            has_any_data = True
        rows.append(
            _build_row(
                label=label,
                kind=kind,
                metric=payload,
                default_missing_reason="данные по рекламе отсутствуют",
            )
        )

    if has_any_data:
        return {"has_data": True, "rows": rows, "message": None}

    source_reason_map = facts.diagnostics.get("source_reason_map")
    reason_map = dict(source_reason_map) if isinstance(source_reason_map, dict) else {}
    reason = str(reason_map.get("ads") or reason_map.get("ads_stats") or reason_map.get("ads_campaigns") or "").strip().lower()
    reason_text_map = {
        "request_failed": "API не вернул данные",
        "auth_failed": "ошибка авторизации API",
        "empty_payload": "API вернул пустой ответ",
        "ok_empty_payload": "API вернул пустой ответ",
        "parse_failed": "ответ API не удалось разобрать",
        "source_missing": "источник недоступен",
        "no_data_for_date": "за выбранную дату данных нет",
    }
    reason_ru = reason_text_map.get(reason, "")
    if reason_ru:
        message = f"Данные по рекламе отсутствуют ({reason_ru})"
    else:
        message = "Данные по рекламе отсутствуют"
    return {"has_data": False, "rows": [], "message": message}


def map_stock_section(facts: FactsBundle) -> list[dict[str, Any]]:
    total = _metric_payload(facts, "stock", "total_stock_units")
    in_stock = _metric_payload(facts, "stock", "in_stock_items_count")
    out_stock = _metric_payload(facts, "stock", "out_of_stock_items_count")

    coverage = "нет данных"
    if in_stock["value"] is not None and out_stock["value"] is not None:
        try:
            in_stock_count = int(float(in_stock["value"]))
            out_stock_count = int(float(out_stock["value"]))
            total_entities = in_stock_count + out_stock_count
            coverage = f"{in_stock_count} SKU в наличии из {total_entities}"
        except (TypeError, ValueError):
            coverage = "нет данных"

    deficit_risk = "нет данных"
    if out_stock["value"] is not None:
        try:
            out_count = float(out_stock["value"])
            deficit_risk = "есть риск дефицита" if out_count > 0 else "риск дефицита низкий"
        except (TypeError, ValueError):
            deficit_risk = "нет данных"

    return [
        _build_row(label="Остаток", kind="count", metric=total, default_missing_reason="данные по остаткам отсутствуют"),
        {
            "label": "Покрытие",
            "value": coverage,
            "status": "confirmed" if coverage != "нет данных" else "unavailable",
            "note": None,
            "reason": None if coverage != "нет данных" else "данные по покрытию отсутствуют",
        },
        {
            "label": "Риск дефицита",
            "value": deficit_risk,
            "status": "confirmed" if deficit_risk != "нет данных" else "unavailable",
            "note": None,
            "reason": None if deficit_risk != "нет данных" else "данные о дефиците отсутствуют",
        },
    ]


def map_health_section(facts: FactsBundle) -> list[dict[str, Any]]:
    key_map = [
        ("Оценка здоровья бизнеса", "business_health_score", "count"),
        ("Статус оценки", "score_status", "count"),
        ("Сигналы риска SKU", "sku_health_signals_count", "count"),
        ("Проблемные SKU", "problematic_sku_count", "count"),
        ("Риск неликвида", "dead_stock_risk_count", "count"),
        ("Риск оверстока", "overstock_risk_count", "count"),
        ("Комментарий к статусу", "business_health_status_note", "count"),
    ]

    rows: list[dict[str, Any]] = []
    for label, key, kind in key_map:
        payload = _metric_payload(facts, "health", key)
        rows.append(
            _build_row(
                label=label,
                kind=kind,
                metric=payload,
                default_missing_reason="данные health-секции отсутствуют",
            )
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
