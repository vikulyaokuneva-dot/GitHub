from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts.report_payload_schema import (
    AbcAnalysisSectionV2,
    AbcSectionSkuItemV2,
    AbcSectionV2,
    AbcSkuItemV2,
    AdsEfficiencySectionV2,
    AdsRowV2,
    AdsSectionV2,
    DiagnosticsRowV2,
    DiagnosticsV2,
    DisplayRowV2,
    FinanceAlignmentNoticeV2,
    FunnelSectionV2,
    FunnelStageRowV2,
    HeroBlockV2,
    HeroKpiCardV2,
    ProfitContributionSectionV2,
    ProfitSkuItemV2,
    QueryProfitabilitySectionV2,
    ReportPayloadV2,
    SectionV2,
    SourceFlagRowV2,
    SkuHealthItemV2,
    SkuHealthSectionV2,
    WarningItemV2,
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _format_display_int(value: Any, unit: str) -> str:
    numeric = _safe_int(value)
    if numeric is None:
        return "нет данных"
    return f"{numeric:,}".replace(",", " ") + f" {unit}"


def _format_display_money(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "нет данных"
    if numeric.is_integer():
        formatted = f"{int(numeric):,}".replace(",", " ")
    else:
        formatted = f"{numeric:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} ₽"


def _format_hero_int(value: Any, unit: str) -> str:
    return _format_display_int(value, unit)


def _format_hero_money(value: Any) -> str:
    return _format_display_money(value)


def _format_display_text(value: Any) -> str:
    return _safe_str(value) or "нет данных"


def _display_status(available: bool, value: Any = None, *, warning: bool = False) -> str:
    if not available or value is None or value == "":
        return "unavailable"
    return "warning" if warning else "ok"


def _display_row(label: str, value: str, *, note: str = "", status: str = "ok") -> DisplayRowV2:
    return {
        "label": _safe_str(label),
        "value": _safe_str(value) or "нет данных",
        "note": _safe_str(note),
        "status": _safe_str(status) or "ok",
    }


def _format_display_percent(value: float | None) -> str:
    if value is None:
        return "нет данных"
    if float(value).is_integer():
        formatted = f"{int(value)}"
    else:
        formatted = f"{value:.2f}".replace(".", ",")
    return f"{formatted}%"


def _format_display_share_percent(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "нет данных"
    display_value = numeric * 100.0 if abs(numeric) <= 1.0 else numeric
    return _format_display_percent(display_value)


def _safe_snapshot_float(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    return _safe_float(value)


def _format_snapshot_percent(value: Any) -> str:
    numeric = _safe_snapshot_float(value)
    if numeric is None:
        return "нет данных"
    if numeric.is_integer():
        formatted = f"{int(numeric)}"
    else:
        formatted = f"{numeric:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}%"


def _funnel_row(stage: str, value: str, *, source: str, status: str, note: str = "") -> FunnelStageRowV2:
    return {
        "stage": _safe_str(stage),
        "value": _safe_str(value) or "нет данных",
        "source": _safe_str(source) or "нет данных",
        "status": _safe_str(status) or "unavailable",
        "note": _safe_str(note),
    }


def _ads_row(label: str, value: str, *, source: str, status: str, note: str = "") -> AdsRowV2:
    return {
        "label": _safe_str(label),
        "value": _safe_str(value) or "нет данных",
        "source": _safe_str(source) or "нет данных",
        "status": _safe_str(status) or "unavailable",
        "note": _safe_str(note),
    }


def _warning(code: str, message: str, *, block: str, level: str = "warning") -> WarningItemV2:
    payload: WarningItemV2 = {
        "code": _safe_str(code),
        "message": _safe_str(message),
        "level": _safe_str(level) or "warning",
        "block": _safe_str(block),
    }
    return payload


def _normalize_debug_warnings(items: Any) -> list[WarningItemV2]:
    warnings: list[WarningItemV2] = []
    if not isinstance(items, list):
        return warnings
    for item in items:
        if isinstance(item, dict):
            message = _safe_str(item.get("message"))
            if not message:
                continue
            warnings.append(
                _warning(
                    _safe_str(item.get("code")) or "debug_warning",
                    message,
                    block=_safe_str(item.get("block")) or "meta",
                    level=_safe_str(item.get("level")) or "warning",
                )
            )
            continue
        message = _safe_str(item)
        if message:
            warnings.append(_warning("debug_warning", message, block="meta"))
    return warnings


def _normalize_diagnostics_warning(item: Any, *, default_block: str) -> DiagnosticsRowV2 | None:
    if isinstance(item, dict):
        message = _safe_str(item.get("message") or item.get("text") or item.get("reason"))
        if not message:
            return None
        return {
            "code": _safe_str(item.get("code") or item.get("type")) or "warning",
            "level": _safe_str(item.get("level") or item.get("severity")) or "warning",
            "block": _safe_str(item.get("block") or item.get("source") or default_block) or default_block,
            "message": message,
        }
    message = _safe_str(item)
    if not message:
        return None
    return {
        "code": "warning",
        "level": "warning",
        "block": default_block,
        "message": message,
    }


def _dedupe_diagnostics_warnings(items: list[DiagnosticsRowV2]) -> list[DiagnosticsRowV2]:
    deduped: list[DiagnosticsRowV2] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (
            _safe_str(item.get("code")),
            _safe_str(item.get("level")),
            _safe_str(item.get("block")),
            _safe_str(item.get("message")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _availability_status(block: dict[str, Any]) -> str:
    if not block:
        return "missing"
    return "ok" if bool(block.get("available", False)) else "unavailable"


def _source_flag(name: str, value: Any, status: str) -> SourceFlagRowV2:
    if isinstance(value, bool):
        value_text = "true" if value else "false"
    elif value is None or value == "":
        value_text = "unknown"
    else:
        value_text = _safe_str(value)
    return {
        "name": _safe_str(name),
        "value": value_text,
        "status": _safe_str(status) or "unknown",
    }


def build_diagnostics_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    builder_warnings: list[dict[str, Any]],
) -> DiagnosticsV2:
    safe_snapshot = _safe_dict(snapshot)
    safe_debug = _safe_dict(debug)
    diagnostics_warnings: list[DiagnosticsRowV2] = []

    for item in builder_warnings if isinstance(builder_warnings, list) else []:
        normalized = _normalize_diagnostics_warning(item, default_block="builder")
        if normalized is not None:
            diagnostics_warnings.append(normalized)

    for source_payload, default_block in (
        (safe_debug.get("warnings"), "debug"),
        (safe_debug.get("source_warnings"), "debug"),
        (safe_snapshot.get("warnings"), "snapshot"),
        (safe_snapshot.get("source_warnings"), "snapshot"),
    ):
        if not isinstance(source_payload, list):
            continue
        for item in source_payload:
            normalized = _normalize_diagnostics_warning(item, default_block=default_block)
            if normalized is not None:
                diagnostics_warnings.append(normalized)

    cabinet_daily = _safe_dict(safe_snapshot.get("cabinet_commerce_daily"))
    finance_daily = _safe_dict(safe_snapshot.get("finance_final_daily"))
    live_daily = _safe_dict(safe_snapshot.get("live_operational"))
    live_orders = _safe_dict(live_daily.get("orders"))
    live_sales = _safe_dict(live_daily.get("sales"))
    live_stocks = _safe_dict(live_daily.get("stocks"))

    cabinet_status = _availability_status(cabinet_daily)
    finance_status = _availability_status(finance_daily)
    if finance_status == "ok" and finance_daily.get("date_aligned") is False:
        finance_status = "lagged"
    debug_present = debug is not None

    source_flags: list[SourceFlagRowV2] = [
        _source_flag("cabinet_commerce.available", bool(cabinet_daily.get("available", False)), cabinet_status),
        _source_flag("cabinet_commerce.status", cabinet_status, cabinet_status),
        _source_flag("cabinet_commerce.source", _safe_str(cabinet_daily.get("source")) or "missing", cabinet_status),
        _source_flag("finance_final.available", bool(finance_daily.get("available", False)), finance_status),
        _source_flag("finance_final.status", finance_status, finance_status),
        _source_flag("finance_final.source", _safe_str(finance_daily.get("source")) or "missing", finance_status),
        _source_flag(
            "finance_final.date_aligned",
            finance_daily.get("date_aligned") if "date_aligned" in finance_daily else None,
            finance_status,
        ),
        _source_flag("live_operational.orders.available", bool(live_orders.get("available", False)), _availability_status(live_orders)),
        _source_flag("live_operational.sales.available", bool(live_sales.get("available", False)), _availability_status(live_sales)),
        _source_flag("live_operational.stocks.available", bool(live_stocks.get("available", False)), _availability_status(live_stocks)),
        _source_flag("debug_present", debug_present, "ok" if debug_present else "missing"),
    ]

    warnings = _dedupe_diagnostics_warnings(diagnostics_warnings)
    return {
        "warnings": warnings,
        "source_flags": source_flags,
        "warnings_count": len(warnings),
    }


def _resolve_buyouts_owner(
    *, cabinet_daily: dict[str, Any], finance_daily: dict[str, Any], warnings: list[WarningItemV2]
) -> tuple[int | None, float | None, str, str]:
    finance_buyouts_count = _safe_int(finance_daily.get("buyouts_count"))
    finance_buyouts_amount = _safe_float(finance_daily.get("buyouts_amount"))
    if finance_buyouts_count is not None or finance_buyouts_amount is not None:
        return (
            finance_buyouts_count,
            finance_buyouts_amount,
            "finance_final_daily",
            _safe_str(finance_daily.get("source")) or "finance_final_daily",
        )

    cabinet_buyouts_count = _safe_int(cabinet_daily.get("buyouts_count"))
    cabinet_buyouts_amount = _safe_float(cabinet_daily.get("buyouts_amount"))
    if cabinet_buyouts_count is not None or cabinet_buyouts_amount is not None:
        warnings.append(
            _warning(
                "buyouts_owner_from_cabinet_commerce",
                "Buyouts are mapped from cabinet_commerce_daily because finance_final_daily does not provide them.",
                block="cabinet_commerce",
            )
        )
        return (
            cabinet_buyouts_count,
            cabinet_buyouts_amount,
            "cabinet_commerce_daily",
            _safe_str(cabinet_daily.get("source")) or "cabinet_commerce_daily",
        )

    warnings.append(
        _warning(
            "buyouts_missing_in_snapshot",
            "Buyouts are missing in both finance_final_daily and cabinet_commerce_daily.",
            block="cabinet_commerce",
        )
    )
    return (None, None, "missing", "missing")


def _build_live_metric(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(block.get("available", False)),
        "source": _safe_str(block.get("source")) or "missing",
        "target_date": _safe_str(block.get("target_date")) or None,
        "count": _safe_int(block.get("count")),
        "amount": _safe_float(block.get("amount")),
        "total_units": _safe_int(block.get("total_units")),
        "snapshot_date": _safe_str(block.get("snapshot_date")) or None,
        "snapshot_kind": _safe_str(block.get("snapshot_kind")) or None,
        "operational_date_reference": _safe_str(block.get("operational_date_reference")) or None,
    }


def _metric_has_value(*values: Any) -> bool:
    return any(_safe_float(value) is not None for value in values)


def _live_metric_available(block: dict[str, Any], *field_names: str) -> bool:
    if not bool(block.get("available", False)):
        return False
    return any(_safe_float(block.get(field_name)) is not None for field_name in field_names)


def _append_once(warnings: list[WarningItemV2], warning: WarningItemV2) -> None:
    code = _safe_str(warning.get("code"))
    if code and any(_safe_str(item.get("code")) == code for item in warnings if isinstance(item, dict)):
        return
    warnings.append(warning)


def _build_commerce_block_with_live_fallback(
    *,
    cabinet_daily: dict[str, Any],
    live_block: dict[str, Any],
    buyouts_count: int | None,
    buyouts_amount: float | None,
    buyouts_owner: str,
    buyouts_source: str,
    warnings: list[WarningItemV2],
) -> dict[str, Any]:
    cabinet_available = bool(cabinet_daily.get("available", False)) and bool(cabinet_daily)
    cabinet_source = _safe_str(cabinet_daily.get("source")) or "missing"
    cabinet_status = "ok" if cabinet_available else "unavailable"
    live_orders = _safe_dict(live_block.get("orders"))
    live_sales = _safe_dict(live_block.get("sales"))

    orders_count = _safe_int(cabinet_daily.get("orders_count"))
    orders_amount = _safe_float(cabinet_daily.get("orders_amount"))
    orders_source = cabinet_source
    orders_note = "Источник: cabinet_commerce_daily"
    orders_status = "ok" if cabinet_available and _metric_has_value(orders_count, orders_amount) else "unavailable"
    orders_fallback = False

    if (not cabinet_available or not _metric_has_value(orders_count, orders_amount)) and _live_metric_available(
        live_orders, "count", "amount"
    ):
        orders_count = _safe_int(live_orders.get("count"))
        orders_amount = _safe_float(live_orders.get("amount"))
        orders_source = _safe_str(live_orders.get("source")) or "orders_api"
        orders_note = "Оперативные заказы из live_operational.orders; fallback because cabinet_commerce_daily is unavailable."
        orders_status = "partial"
        orders_fallback = True

    confirmed_buyouts = _metric_has_value(buyouts_count, buyouts_amount)
    buyouts_status = "ok" if confirmed_buyouts else "unavailable"
    buyouts_note = (
        f"Подтвержденные выкупы из {buyouts_owner}."
        if confirmed_buyouts
        else "Подтвержденные выкупы отсутствуют в finance_final_daily и cabinet_commerce_daily."
    )

    sales_count = None
    sales_amount = None
    sales_source = "missing"
    sales_note = ""
    sales_status = "unavailable"
    sales_fallback = False
    if _live_metric_available(live_sales, "count", "amount"):
        sales_count = _safe_int(live_sales.get("count"))
        sales_amount = _safe_float(live_sales.get("amount"))
        sales_source = _safe_str(live_sales.get("source")) or "sales_api"
        sales_status = "partial" if not confirmed_buyouts else "ok"
        sales_fallback = not cabinet_available or not confirmed_buyouts
        sales_note = (
            "Оперативные продажи из live_operational.sales; это не подтвержденные выкупы."
            if sales_fallback
            else "Оперативные продажи из live_operational.sales."
        )

    if orders_fallback or sales_fallback:
        _append_once(
            warnings,
            _warning(
                "commerce_filled_from_live_operational",
                "Коммерческий блок частично заполнен из live_operational, потому что cabinet_commerce_daily недоступен.",
                block="report_payload_builder",
            ),
        )
    if sales_fallback:
        _append_once(
            warnings,
            _warning(
                "operational_sales_not_confirmed_buyouts",
                "Оперативные продажи из sales_api показаны отдельно и не считаются подтвержденными выкупами.",
                block="live_operational_fallback",
            ),
        )

    return {
        "available": cabinet_available,
        "status": cabinet_status,
        "source": cabinet_source,
        "owner_block": "cabinet_commerce_daily",
        "target_date": _safe_str(cabinet_daily.get("target_date")) or None,
        "orders_count": orders_count,
        "orders_amount": orders_amount,
        "orders_source": orders_source,
        "orders_note": orders_note,
        "orders_status": orders_status,
        "orders_fallback": orders_fallback,
        "buyouts_count": buyouts_count,
        "buyouts_amount": buyouts_amount,
        "buyouts_source": buyouts_source,
        "buyouts_note": buyouts_note,
        "buyouts_status": buyouts_status,
        "sales_count": sales_count,
        "sales_amount": sales_amount,
        "sales_source": sales_source,
        "sales_note": sales_note,
        "sales_status": sales_status,
        "sales_fallback": sales_fallback,
    }


def build_finance_alignment_notice_v2(finance_final: dict[str, Any] | None) -> FinanceAlignmentNoticeV2:
    finance = _safe_dict(finance_final)
    source = _safe_str(finance.get("source")) or "finance_final_daily"
    target_date = _safe_str(finance.get("target_date")) or None
    actual_date = _safe_str(finance.get("actual_date")) or None

    if not finance or not bool(finance.get("available", False)):
        return {
            "state": "unavailable",
            "title": "Финансовый контур недоступен",
            "lines": ["Финансовые данные за день не получены из wb_api_core."],
            "source": source,
            "target_date": target_date,
            "actual_date": actual_date,
        }

    if finance.get("date_aligned") is False:
        return {
            "state": "lagged",
            "title": "Финансовые данные с лагом",
            "lines": [
                "Финансовые данные относятся не к операционному дню отчёта.",
                f"Операционный день: {target_date or 'unknown'}",
                f"Фактическая дата финансов: {actual_date or 'unknown'}",
            ],
            "source": source,
            "target_date": target_date,
            "actual_date": actual_date,
        }

    return {
        "state": "ok",
        "title": "",
        "lines": [],
        "source": source,
        "target_date": target_date,
        "actual_date": actual_date,
    }


def build_hero_v2(
    *,
    meta: dict[str, Any],
    cabinet_commerce: dict[str, Any],
    finance_final: dict[str, Any],
    live_operational: dict[str, Any],
    warnings: list[WarningItemV2],
) -> HeroBlockV2:
    cabinet = _safe_dict(cabinet_commerce)
    finance = _safe_dict(finance_final)
    live = _safe_dict(live_operational)
    stocks = _safe_dict(live.get("stocks"))

    cabinet_available = bool(cabinet.get("available", False))
    finance_available = bool(finance.get("available", False))
    finance_status = _safe_str(finance.get("status")) or ("ok" if finance_available else "unavailable")
    stocks_available = bool(stocks.get("available", False))

    orders_status = _safe_str(cabinet.get("orders_status")) or (
        "ok" if cabinet_available and cabinet.get("orders_count") is not None else "unavailable"
    )
    buyouts_status = _safe_str(cabinet.get("buyouts_status")) or (
        "ok" if cabinet_available and cabinet.get("buyouts_count") is not None else "unavailable"
    )
    sales_status = _safe_str(cabinet.get("sales_status")) or "unavailable"
    show_operational_sales = (
        cabinet.get("buyouts_count") is None
        and cabinet.get("buyouts_amount") is None
        and (cabinet.get("sales_count") is not None or cabinet.get("sales_amount") is not None)
    )
    payout_status = "unavailable"
    if finance_available and finance.get("seller_payout") is not None:
        payout_status = "warning" if finance_status == "lagged" else "ok"
    stocks_status = "ok" if stocks_available and stocks.get("total_units") is not None else "unavailable"
    orders_subvalue = _format_hero_money(cabinet.get("orders_amount"))
    if bool(cabinet.get("orders_fallback", False)):
        orders_subvalue = (
            f"{orders_subvalue}; {_safe_str(cabinet.get('orders_source')) or 'orders_api'}; оперативно"
        )

    cards: list[HeroKpiCardV2] = [
        {
            "label": "Заказы",
            "value": _format_hero_int(cabinet.get("orders_count"), "шт"),
            "subvalue": orders_subvalue,
            "status": orders_status,
        },
        {
            "label": "Продажи" if show_operational_sales else "Выкупы",
            "value": _format_hero_int(
                cabinet.get("sales_count") if show_operational_sales else cabinet.get("buyouts_count"),
                "шт",
            ),
            "subvalue": (
                f"{_format_hero_money(cabinet.get('sales_amount'))}; {_safe_str(cabinet.get('sales_source')) or 'sales_api'}; оперативно"
                if show_operational_sales
                else _format_hero_money(cabinet.get("buyouts_amount"))
            ),
            "status": sales_status if show_operational_sales else buyouts_status,
        },
        {
            "label": "К перечислению",
            "value": _format_hero_money(finance.get("seller_payout")),
            "subvalue": _safe_str(finance.get("source")) or "finance_final_daily",
            "status": payout_status,
        },
        {
            "label": "Остатки",
            "value": _format_hero_int(stocks.get("total_units"), "шт"),
            "subvalue": _safe_str(stocks.get("snapshot_date")) or "дата не указана",
            "status": stocks_status,
        },
    ]

    if not cabinet_available and not finance_available:
        data_status = "unavailable"
        data_status_message = "Основные данные кабинета и финансов недоступны."
    elif not cabinet_available or not finance_available or finance_status == "lagged":
        data_status = "partial"
        data_status_message = "Часть основных данных недоступна или пришла с лагом."
    elif warnings:
        data_status = "warning"
        data_status_message = "Данные получены, есть предупреждения по источникам."
    else:
        data_status = "ok"
        data_status_message = "Данные получены из wb_api_core."

    seller_id = _safe_str(meta.get("seller_id")) or "unknown"
    report_date = _safe_str(meta.get("operational_date") or meta.get("report_date")) or "unknown"
    return {
        "title": "Ежедневный отчёт WB",
        "subtitle": f"Кабинет: {seller_id} | Дата: {report_date}",
        "cards": cards,
        "data_status": data_status,
        "data_status_message": data_status_message,
    }


def build_commerce_section_v2(cabinet_commerce: dict[str, Any]) -> SectionV2:
    commerce = _safe_dict(cabinet_commerce)
    available = bool(commerce.get("available", False))
    source = _format_display_text(commerce.get("source"))
    orders_source = _format_display_text(commerce.get("orders_source") or commerce.get("source"))
    buyouts_source = _format_display_text(commerce.get("buyouts_source") or commerce.get("source"))
    sales_source = _format_display_text(commerce.get("sales_source"))
    owner = _format_display_text(commerce.get("owner_block"))
    target_date = _format_display_text(commerce.get("target_date"))
    orders_fallback = bool(commerce.get("orders_fallback", False))
    sales_fallback = bool(commerce.get("sales_fallback", False))
    has_buyouts = _metric_has_value(commerce.get("buyouts_count"), commerce.get("buyouts_amount"))
    has_sales = _metric_has_value(commerce.get("sales_count"), commerce.get("sales_amount"))
    status = "ok" if available else ("partial" if (orders_fallback or sales_fallback) else "unavailable")

    rows: list[DisplayRowV2] = [
        _display_row(
            "Заказы",
            _format_display_int(commerce.get("orders_count"), "шт"),
            note=_safe_str(commerce.get("orders_note")) or f"Дата: {target_date}; источник: {orders_source}",
            status=_safe_str(commerce.get("orders_status")) or _display_status(available, commerce.get("orders_count")),
        ),
        _display_row(
            "Сумма заказов",
            _format_display_money(commerce.get("orders_amount")),
            note=f"Источник: {orders_source}",
            status=_safe_str(commerce.get("orders_status")) or _display_status(available, commerce.get("orders_amount")),
        ),
    ]
    if has_buyouts:
        rows.extend(
            [
                _display_row(
                    "Выкупы",
                    _format_display_int(commerce.get("buyouts_count"), "шт"),
                    note=_safe_str(commerce.get("buyouts_note")) or f"Владелец: {owner}",
                    status=_safe_str(commerce.get("buyouts_status")) or _display_status(available, commerce.get("buyouts_count")),
                ),
                _display_row(
                    "Сумма выкупов",
                    _format_display_money(commerce.get("buyouts_amount")),
                    note=f"Источник: {buyouts_source}",
                    status=_safe_str(commerce.get("buyouts_status")) or _display_status(available, commerce.get("buyouts_amount")),
                ),
            ]
        )
    elif has_sales:
        rows.extend(
            [
                _display_row(
                    "Оперативные продажи",
                    _format_display_int(commerce.get("sales_count"), "шт"),
                    note=_safe_str(commerce.get("sales_note"))
                    or "Оперативные продажи из live_operational.sales; не подтвержденные выкупы.",
                    status=_safe_str(commerce.get("sales_status")) or "partial",
                ),
                _display_row(
                    "Сумма оперативных продаж",
                    _format_display_money(commerce.get("sales_amount")),
                    note=f"Источник: {sales_source}; не confirmed buyouts",
                    status=_safe_str(commerce.get("sales_status")) or "partial",
                ),
            ]
        )
    else:
        rows.extend(
            [
                _display_row(
                    "Выкупы",
                    _format_display_int(None, "шт"),
                    note=_safe_str(commerce.get("buyouts_note")) or "Подтвержденные выкупы отсутствуют.",
                    status="unavailable",
                ),
                _display_row(
                    "Сумма выкупов",
                    _format_display_money(None),
                    note=f"Источник: {buyouts_source}",
                    status="unavailable",
                ),
            ]
        )
    rows.append(
        _display_row(
            "Источник",
            source,
            note=f"Блок: {owner}; fallback: {'live_operational' if (orders_fallback or sales_fallback) else 'нет'}",
            status=status,
        )
    )
    return {
        "title": "Коммерция",
        "subtitle": (
            "Заказы и оперативные продажи частично заполнены из live_operational."
            if (orders_fallback or sales_fallback)
            else "Заказы и выкупы из core-safe cabinet_commerce."
        ),
        "rows": rows,
        "status": status,
    }


def _clean_core_upper_funnel(snapshot: dict[str, Any]) -> dict[str, Any]:
    safe_snapshot = _safe_dict(snapshot)
    candidates = (
        safe_snapshot.get("funnel_core"),
        safe_snapshot.get("core_funnel"),
        safe_snapshot.get("upper_funnel_core"),
        safe_snapshot.get("sales_funnel_core"),
    )
    for candidate in candidates:
        block = _safe_dict(candidate)
        if block and bool(block.get("available", False)):
            return block
    return {}


def _upper_funnel_stage_row(
    stage: str,
    block: dict[str, Any],
    field_names: tuple[str, ...],
    *,
    default_source: str = "wb_api_core",
) -> FunnelStageRowV2:
    for field_name in field_names:
        if field_name in block:
            value = _safe_int(block.get(field_name))
            if value is not None:
                return _funnel_row(
                    stage,
                    _format_display_int(value, "шт"),
                    source=_safe_str(block.get("source")) or default_source,
                    status="ok",
                    note="Данные получены из clean core block.",
                )
    return _funnel_row(
        stage,
        "нет данных",
        source="нет clean core source",
        status="unavailable",
        note="Источник верхней части воронки отсутствует в snapshot.",
    )


def _funnel_daily_count_row(stage: str, block: dict[str, Any], field_name: str, *, source: str) -> FunnelStageRowV2:
    value = _safe_int(block.get(field_name))
    return _funnel_row(
        stage,
        _format_display_int(value, "шт"),
        source=source,
        status="ok" if value is not None else "unavailable",
        note="Данные получены из snapshot.funnel_daily.",
    )


def _funnel_daily_rate_row(stage: str, block: dict[str, Any], field_name: str, *, source: str) -> FunnelStageRowV2:
    value = _safe_snapshot_float(block.get(field_name))
    return _funnel_row(
        stage,
        _format_snapshot_percent(value),
        source=source,
        status="ok" if value is not None else "unavailable",
        note="Данные получены из snapshot.funnel_daily.",
    )


def build_funnel_section_v2(
    snapshot: dict[str, Any],
    cabinet_commerce: dict[str, Any],
    debug: dict[str, Any] | None,
) -> FunnelSectionV2:
    _ = debug
    safe_snapshot = _safe_dict(snapshot)
    funnel_daily = _safe_dict(safe_snapshot.get("funnel_daily"))
    if funnel_daily and bool(funnel_daily.get("available", False)):
        source = _safe_str(funnel_daily.get("source")) or "sales_funnel_api"
        status = _safe_str(funnel_daily.get("status")).lower() or "ok"
        if status not in {"ok", "partial"}:
            status = "partial"
        message = (
            "Воронка собрана из sales_funnel_api."
            if status == "ok"
            else "Воронка частично доступна из sales_funnel_api."
        )
        rows: list[FunnelStageRowV2] = [
            _funnel_daily_count_row("Открытия карточек", funnel_daily, "open_count", source=source),
            _funnel_daily_count_row("Корзина", funnel_daily, "cart_count", source=source),
            _funnel_daily_count_row("Заказы", funnel_daily, "orders_count", source=source),
            _funnel_daily_count_row("Выкупы", funnel_daily, "buyouts_count", source=source),
            _funnel_daily_rate_row("Открытие → корзина", funnel_daily, "open_to_cart_rate", source=source),
            _funnel_daily_rate_row("Корзина → заказ", funnel_daily, "cart_to_order_rate", source=source),
            _funnel_daily_rate_row("Заказ → выкуп", funnel_daily, "order_to_buyout_rate", source=source),
        ]
        return {
            "title": "Воронка продаж",
            "subtitle": "Воронка из snapshot.funnel_daily.",
            "rows": rows,
            "status": status,
            "message": message,
        }

    cabinet = _safe_dict(cabinet_commerce)
    cabinet_available = bool(cabinet.get("available", False))
    cabinet_source = _safe_str(cabinet.get("source")) or "cabinet_commerce_daily"
    live_daily = _safe_dict(safe_snapshot.get("live_operational"))
    live_orders = _safe_dict(live_daily.get("orders"))
    live_sales = _safe_dict(live_daily.get("sales"))
    orders_count = _safe_int(cabinet.get("orders_count"))
    buyouts_count = _safe_int(cabinet.get("buyouts_count"))
    sales_count = None
    orders_source = cabinet_source
    sales_source = "нет данных"
    orders_note = "Нижняя часть воронки из cabinet_commerce."
    sales_note = "Нижняя часть воронки из cabinet_commerce."
    orders_status = _display_status(cabinet_available, orders_count)
    buyouts_status = _display_status(cabinet_available, buyouts_count)
    if (not cabinet_available or orders_count is None) and _live_metric_available(live_orders, "count"):
        orders_count = _safe_int(live_orders.get("count"))
        orders_source = _safe_str(live_orders.get("source")) or "orders_api"
        orders_status = "partial"
        orders_note = "Оперативные заказы из live_operational.orders; fallback, не cabinet_commerce."
    if buyouts_count is None and _live_metric_available(live_sales, "count"):
        sales_count = _safe_int(live_sales.get("count"))
        sales_source = _safe_str(live_sales.get("source")) or "sales_api"
        sales_note = "Оперативные продажи из live_operational.sales; не подтвержденные выкупы."
        if not cabinet_available:
            buyouts_status = "unavailable"
    upper = _clean_core_upper_funnel(snapshot)

    rows: list[FunnelStageRowV2] = [
        _upper_funnel_stage_row("Показы", upper, ("views", "impressions", "shows")),
        _upper_funnel_stage_row("Клики", upper, ("clicks", "click_count")),
        _upper_funnel_stage_row("Корзина", upper, ("add_to_cart", "cart_count", "basket_count")),
        _funnel_row(
            "Заказы",
            _format_display_int(orders_count, "шт"),
            source=orders_source,
            status=orders_status,
            note=orders_note,
        ),
    ]
    if buyouts_count is not None:
        rows.append(
            _funnel_row(
                "Выкупы",
                _format_display_int(buyouts_count, "шт"),
                source=cabinet_source,
                status=buyouts_status,
                note=sales_note,
            )
        )
    elif sales_count is not None:
        rows.append(
            _funnel_row(
                "Оперативные продажи",
                _format_display_int(sales_count, "шт"),
                source=sales_source,
                status="partial",
                note=sales_note,
            )
        )
    else:
        rows.append(
            _funnel_row(
                "Выкупы",
                _format_display_int(buyouts_count, "шт"),
                source=cabinet_source,
                status=buyouts_status,
                note=sales_note,
            )
        )

    conversion: float | None = None
    conversion_status = "unavailable"
    conversion_note = "Недостаточно данных для расчёта."
    if orders_count is not None and orders_count > 0 and buyouts_count is not None:
        conversion = round(float(buyouts_count) / float(orders_count) * 100.0, 2)
        conversion_status = "ok"
        conversion_note = "Рассчитано в builder из заказов и выкупов."
    rows.append(
        _funnel_row(
            "Конверсия заказ → выкуп",
            _format_display_percent(conversion),
            source=cabinet_source if conversion_status == "ok" else "нет данных",
            status=conversion_status,
            note=conversion_note,
        )
    )

    lower_available = orders_count is not None or buyouts_count is not None or sales_count is not None
    all_rows_available = all(row.get("status") == "ok" for row in rows)
    if all_rows_available:
        status = "ok"
        message = "Воронка собрана из clean core данных."
    elif lower_available:
        status = "partial"
        message = "Воронка частично заполнена из core snapshot; оперативные продажи не считаются подтвержденными выкупами."
    else:
        status = "unavailable"
        message = "Нет core-safe данных для заказов и выкупов."

    return {
        "title": "Воронка продаж",
        "subtitle": "Минимальная воронка только из wb_api_core snapshot.",
        "rows": rows,
        "status": status,
        "message": message,
    }


def _first_numeric(block: dict[str, Any], field_names: tuple[str, ...]) -> float | None:
    for field_name in field_names:
        if field_name in block:
            value = _safe_float(block.get(field_name))
            if value is not None:
                return value
    return None


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return [item for item in value.values()]
    return []


def _safe_dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in _safe_list(value) if isinstance(item, dict)]


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_value(path: Path) -> Any:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _artifact_dirs(artifact_dir: str | Path | None) -> list[Path]:
    if artifact_dir is None:
        return []
    start = Path(artifact_dir)
    if start.is_file():
        start = start.parent

    candidates: list[Path] = []
    for item in (start, *start.parents):
        candidates.append(item)
        if item.name == "artifacts":
            candidates.append(item)
        nested = item / "artifacts"
        if nested.is_dir():
            candidates.append(nested)

    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        try:
            key = str(item.resolve())
        except OSError:
            key = str(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _ads_artifact_dirs(artifact_dir: str | Path | None) -> list[Path]:
    return _artifact_dirs(artifact_dir)


def _load_ads_artifacts_from_dir(artifact_dir: str | Path | None) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    filenames = {
        "advertising_efficiency": "advertising_efficiency.json",
        "advertising_efficiency_summary": "advertising_efficiency_summary.json",
        "portfolio_ads_summary": "portfolio_ads_summary.json",
        "query_profitability": "query_profitability.json",
        "keyword_monitoring": "keyword_monitoring.json",
    }
    for directory in _ads_artifact_dirs(artifact_dir):
        for key, filename in filenames.items():
            if key in loaded:
                continue
            payload = _read_json_dict(directory / filename)
            if payload:
                loaded[key] = payload
        if len(loaded) == len(filenames):
            break
    return loaded


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        block = _safe_dict(value)
        if block:
            return block
    return {}


def _pick_numeric(*candidates: tuple[dict[str, Any], tuple[str, ...]]) -> float | None:
    for block, names in candidates:
        value = _first_numeric(block, names)
        if value is not None:
            return value
    return None


def _sum_row_numeric(rows: list[dict[str, Any]], *field_names: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        for field_name in field_names:
            if field_name not in row:
                continue
            value = _safe_float(row.get(field_name))
            if value is None:
                continue
            total += value
            seen = True
            break
    return round(total, 4) if seen else None


def _safe_divide(numerator: Any, denominator: Any) -> float | None:
    top = _safe_float(numerator)
    bottom = _safe_float(denominator)
    if top is None or bottom is None or bottom <= 0:
        return None
    return top / bottom


def _format_display_number(value: Any, *, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "нет данных"
    if numeric.is_integer():
        return f"{int(numeric):,}".replace(",", " ")
    return f"{numeric:,.{digits}f}".replace(",", " ").replace(".", ",")


def _format_display_multiplier(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "нет данных"
    return f"{numeric:,.2f}x".replace(",", " ").replace(".", ",")


def _normalize_ads_warnings(items: Any) -> list[WarningItemV2]:
    warnings: list[WarningItemV2] = []
    for item in _safe_list(items):
        if isinstance(item, dict):
            message = _safe_str(item.get("message") or item.get("text") or item.get("reason"))
            if not message:
                continue
            warnings.append(
                _warning(
                    _safe_str(item.get("code")) or "advertising_efficiency_warning",
                    message,
                    block=_safe_str(item.get("block")) or "advertising_efficiency",
                    level=_safe_str(item.get("level")) or "warning",
                )
            )
            continue
        message = _safe_str(item)
        if message:
            warnings.append(_warning("advertising_efficiency_warning", message, block="advertising_efficiency"))
    return warnings


def _query_key(row: dict[str, Any]) -> tuple[float, float, str]:
    return (
        _safe_float(row.get("profit")) or 0.0,
        _safe_float(row.get("ROMI")) or _safe_float(row.get("romi")) or 0.0,
        _safe_str(row.get("query")),
    )


def _brief_query_rows(rows: list[dict[str, Any]], *, classification: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        row_classification = _safe_str(row.get("classification")).lower()
        if classification is not None and row_classification != classification:
            continue
        selected.append(
            {
                "query": _safe_str(row.get("query")),
                "sku": row.get("sku"),
                "ad_spend": _safe_float(row.get("ad_spend")),
                "orders": _safe_float(row.get("orders")),
                "buyouts": _safe_float(row.get("buyouts")),
                "revenue": _safe_float(row.get("revenue")),
                "profit": _safe_float(row.get("profit")),
                "ROMI": _safe_float(row.get("ROMI") or row.get("romi")),
                "classification": row_classification or _safe_str(row.get("classification")),
                "confidence": _safe_str(row.get("confidence")),
            }
        )

    if classification == "unprofitable":
        selected.sort(key=_query_key)
    else:
        selected.sort(key=_query_key, reverse=True)
    return selected[:limit]


def _ads_query_rows_from_sources(
    advertising_efficiency: dict[str, Any],
    query_profitability: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = _safe_dict_list(query_profitability.get("items"))
    if rows:
        return rows
    rows = _safe_dict_list(advertising_efficiency.get("query_performance"))
    if rows:
        return rows
    return _safe_dict_list(advertising_efficiency.get("queries"))


def _ads_recommendations(signals: list[dict[str, Any]], top_unprofitable: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    for signal in signals:
        recommendation = _safe_str(signal.get("recommendation"))
        if recommendation and recommendation not in recommendations:
            recommendations.append(recommendation)
        if len(recommendations) >= 5:
            return recommendations
    if top_unprofitable:
        recommendations.append("Сократить ставки или остановить запросы с отрицательной прибылью до пересборки семантики.")
    return recommendations


def _ads_status(
    *,
    artifact_present: bool,
    raw_status: str,
    analysis_mode: str,
    values: list[Any],
) -> str:
    if not artifact_present:
        return "no_data"
    if raw_status == "disabled" or analysis_mode == "disabled":
        return "disabled"
    useful_values = [value for value in values if _safe_float(value) is not None]
    if not useful_values:
        return "insufficient_data"
    if raw_status == "partial" or analysis_mode == "preview":
        return "partial"
    required_values = values[:4]
    if any(_safe_float(value) is None for value in required_values):
        return "partial"
    return "ok"


def _ads_metric_status(section_status: str, value: Any) -> str:
    if _safe_float(value) is not None:
        return "ok"
    if section_status in {"no_data", "disabled", "insufficient_data"}:
        return section_status
    return "unavailable"


def _build_ads_metric_rows(section: AdsEfficiencySectionV2) -> list[AdsRowV2]:
    source = _safe_str(section.get("source")) or "advertising_efficiency"
    status = _safe_str(section.get("status")) or "no_data"
    metric_specs: list[tuple[str, Any, str, str]] = [
        ("Расход на рекламу", section.get("spend"), "money", "portfolio_ad_spend / total_ad_spend"),
        ("Показы", section.get("impressions"), "int", "aggregated from advertising efficiency rows"),
        ("Клики", section.get("clicks"), "int", "aggregated from advertising efficiency rows"),
        ("CTR", section.get("ctr"), "percent", "clicks / impressions"),
        ("CPC", section.get("cpc"), "money", "spend / clicks"),
        ("CPM", section.get("cpm"), "money", "spend * 1000 / impressions"),
        ("Заказы из рекламы", section.get("ad_orders"), "number", "portfolio_orders_from_ads"),
        ("Выручка из рекламы", section.get("ad_revenue"), "money", "portfolio_revenue_from_ads"),
        ("Выкупы из рекламы", section.get("ad_buyouts"), "number", "portfolio_buyouts_from_ads"),
        ("ДРР", section.get("drr"), "percent", "portfolio_DRR"),
        ("ROAS", section.get("roas"), "multiplier", "revenue / spend"),
        ("ROMI", section.get("romi"), "percent", "portfolio_ROMI"),
        ("CPO", section.get("cpo"), "money", "portfolio_CPO"),
        ("Прибыль от рекламы", section.get("profit_from_ads"), "money", "portfolio_profit_from_ads"),
        ("Потери рекламы", section.get("wasted_spend"), "money", "sum of loss query spend"),
        ("Неэффективных запросов", section.get("inefficient_items_count"), "int", "query_profitability summary"),
    ]
    rows: list[AdsRowV2] = []
    for label, value, value_type, note in metric_specs:
        if value_type == "money":
            formatted = _format_display_money(value)
        elif value_type == "int":
            formatted = _format_display_int(value, "шт")
        elif value_type == "number":
            formatted = _format_display_number(value, digits=2)
        elif value_type == "percent":
            formatted = _format_display_percent(_safe_float(value))
        elif value_type == "multiplier":
            formatted = _format_display_multiplier(value)
        else:
            formatted = _format_display_text(value)
        rows.append(
            _ads_row(
                label,
                formatted,
                source=source if _safe_float(value) is not None else "нет данных",
                status=_ads_metric_status(status, value),
                note=note,
            )
        )
    return rows


def build_ads_efficiency_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
) -> AdsEfficiencySectionV2:
    _ = debug
    safe_snapshot = _safe_dict(snapshot)
    artifacts = _load_ads_artifacts_from_dir(artifact_dir)

    advertising_efficiency = _first_dict(
        safe_snapshot.get("advertising_efficiency"),
        artifacts.get("advertising_efficiency"),
        safe_snapshot.get("advertising_efficiency_daily"),
        safe_snapshot.get("ads_efficiency_daily"),
    )
    summary = _first_dict(
        advertising_efficiency.get("portfolio_ads_summary"),
        advertising_efficiency.get("advertising_efficiency_summary"),
        advertising_efficiency.get("summary"),
        safe_snapshot.get("portfolio_ads_summary"),
        safe_snapshot.get("advertising_efficiency_summary"),
        artifacts.get("portfolio_ads_summary"),
        artifacts.get("advertising_efficiency_summary"),
    )
    query_profitability = _first_dict(
        advertising_efficiency.get("query_profitability"),
        safe_snapshot.get("query_profitability"),
        artifacts.get("query_profitability"),
    )
    query_summary = _safe_dict(query_profitability.get("summary"))
    query_rows = _ads_query_rows_from_sources(advertising_efficiency, query_profitability)
    sku_rows = _safe_dict_list(advertising_efficiency.get("sku_performance"))
    signals = _safe_dict_list(advertising_efficiency.get("signals"))
    artifact_present = bool(advertising_efficiency or summary or query_profitability)

    source_payload = _safe_dict(advertising_efficiency.get("source"))
    source = (
        _safe_str(source_payload.get("query_source"))
        or _safe_str(advertising_efficiency.get("source"))
        or _safe_str(summary.get("source"))
        or "advertising_efficiency_artifacts"
    )
    raw_status = _safe_str(advertising_efficiency.get("status") or query_profitability.get("status")).lower()
    analysis_mode = _safe_str(
        advertising_efficiency.get("analysis_mode")
        or summary.get("analysis_mode")
        or query_profitability.get("analysis_mode")
    ).lower()

    spend = _pick_numeric(
        (summary, ("portfolio_ad_spend", "total_ad_spend", "spend", "ad_spend", "ads_spend")),
        (advertising_efficiency, ("portfolio_ad_spend", "total_ad_spend", "spend", "ad_spend", "ads_spend")),
    )
    impressions = _safe_int(
        _pick_numeric(
            (summary, ("impressions", "ad_impressions")),
            (advertising_efficiency, ("impressions", "ad_impressions")),
        )
    )
    clicks = _safe_int(
        _pick_numeric(
            (summary, ("clicks", "ad_clicks")),
            (advertising_efficiency, ("clicks", "ad_clicks")),
        )
    )
    if impressions is None:
        impressions = _safe_int(_sum_row_numeric(query_rows or sku_rows, "impressions"))
    if clicks is None:
        clicks = _safe_int(_sum_row_numeric(query_rows or sku_rows, "clicks"))

    ad_orders = _pick_numeric(
        (summary, ("portfolio_orders_from_ads", "orders_from_ads", "ad_orders", "ads_orders")),
        (advertising_efficiency, ("portfolio_orders_from_ads", "orders_from_ads", "ad_orders", "ads_orders")),
    )
    ad_revenue = _pick_numeric(
        (summary, ("portfolio_revenue_from_ads", "revenue_from_ads", "ad_revenue", "ads_revenue")),
        (advertising_efficiency, ("portfolio_revenue_from_ads", "revenue_from_ads", "ad_revenue", "ads_revenue")),
    )
    ad_buyouts = _pick_numeric(
        (summary, ("portfolio_buyouts_from_ads", "buyouts_from_ads", "ad_buyouts", "ads_buyouts")),
        (advertising_efficiency, ("portfolio_buyouts_from_ads", "buyouts_from_ads", "ad_buyouts", "ads_buyouts")),
    )
    profit_from_ads = _pick_numeric(
        (summary, ("portfolio_profit_from_ads", "profit_from_ads")),
        (advertising_efficiency, ("portfolio_profit_from_ads", "profit_from_ads")),
    )
    drr = _pick_numeric((summary, ("portfolio_DRR", "DRR", "drr")), (advertising_efficiency, ("DRR", "drr")))
    if drr is None:
        drr_rate = _safe_divide(spend, ad_revenue)
        drr = round(drr_rate * 100.0, 4) if drr_rate is not None else None
    romi = _pick_numeric(
        (summary, ("portfolio_ROMI", "ROMI", "romi")),
        (advertising_efficiency, ("portfolio_ROMI", "ROMI", "romi")),
    )
    cpo = _pick_numeric((summary, ("portfolio_CPO", "CPO", "cpo")), (advertising_efficiency, ("CPO", "cpo")))
    if cpo is None:
        cpo = _safe_divide(spend, ad_orders)
    ctr = _pick_numeric((summary, ("CTR", "ctr")), (advertising_efficiency, ("CTR", "ctr")))
    if ctr is None:
        ctr_rate = _safe_divide(clicks, impressions)
        ctr = round(ctr_rate * 100.0, 4) if ctr_rate is not None else None
    cpc = _pick_numeric((summary, ("CPC", "cpc")), (advertising_efficiency, ("CPC", "cpc")))
    if cpc is None:
        cpc = _safe_divide(spend, clicks)
    cpm = _pick_numeric((summary, ("CPM", "cpm")), (advertising_efficiency, ("CPM", "cpm")))
    if cpm is None:
        cpm_rate = _safe_divide(spend, impressions)
        cpm = round(cpm_rate * 1000.0, 4) if cpm_rate is not None else None
    roas = _pick_numeric((summary, ("ROAS", "roas")), (advertising_efficiency, ("ROAS", "roas")))
    if roas is None:
        roas = _safe_divide(ad_revenue, spend)

    top_profitable_queries = _safe_dict_list(summary.get("top_profitable_queries")) or _brief_query_rows(
        query_rows, classification="profitable", limit=5
    )
    top_unprofitable_queries = _safe_dict_list(summary.get("top_unprofitable_queries")) or _brief_query_rows(
        query_rows, classification="unprofitable", limit=5
    )
    high_potential_queries = _safe_dict_list(summary.get("high_potential_queries")) or [
        row for row in top_profitable_queries if (_safe_float(row.get("ROMI")) or 0.0) >= 20.0
    ][:5]
    all_unprofitable = _brief_query_rows(query_rows, classification="unprofitable", limit=1000)
    if query_rows:
        wasted_spend = _sum_row_numeric(all_unprofitable, "ad_spend")
        inefficient_items_count = len(all_unprofitable)
    else:
        wasted_spend = None
        inefficient_items_count = _safe_int(query_summary.get("unprofitable"))
    if inefficient_items_count is None:
        inefficient_items_count = _safe_int(summary.get("inefficient_items_count"))

    warnings = _normalize_ads_warnings(advertising_efficiency.get("warnings"))
    values_for_status = [spend, ad_orders, ad_revenue, drr, romi, cpo, impressions, clicks]
    status = _ads_status(
        artifact_present=artifact_present,
        raw_status=raw_status,
        analysis_mode=analysis_mode,
        values=values_for_status,
    )

    if status == "no_data":
        message = "Данные advertising_efficiency отсутствуют в snapshot и artifacts."
    elif status == "disabled":
        message = "Рекламная аналитика отключена или рекламные данные отсутствуют."
    elif status == "insufficient_data":
        message = "Advertising artifacts найдены, но полезных метрик недостаточно."
    elif status == "partial":
        message = "Рекламная эффективность доступна частично; пропуски не заменялись нулями."
    else:
        message = "Рекламная эффективность собрана из advertising_efficiency artifacts."

    section: AdsEfficiencySectionV2 = {
        "title": "Реклама",
        "subtitle": "Эффективность рекламы из advertising_efficiency artifacts.",
        "status": status,
        "source": source,
        "message": message,
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": ctr,
        "cpc": cpc,
        "cpm": cpm,
        "ad_orders": ad_orders,
        "ad_revenue": ad_revenue,
        "ad_buyouts": ad_buyouts,
        "drr": drr,
        "roas": roas,
        "romi": romi,
        "cpo": cpo,
        "profit_from_ads": profit_from_ads,
        "wasted_spend": wasted_spend,
        "inefficient_items_count": inefficient_items_count,
        "top_profitable_queries": top_profitable_queries,
        "top_unprofitable_queries": top_unprofitable_queries,
        "high_potential_queries": high_potential_queries,
        "warnings": warnings,
        "loss_rows": top_unprofitable_queries,
        "opportunity_rows": high_potential_queries or top_profitable_queries,
        "recommendations": _ads_recommendations(signals, top_unprofitable_queries),
    }
    section["metric_rows"] = _build_ads_metric_rows(section)
    return section


def build_ads_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
    ads_efficiency_section: AdsEfficiencySectionV2 | None = None,
) -> AdsSectionV2:
    section = ads_efficiency_section or build_ads_efficiency_section_v2(
        snapshot,
        debug,
        artifact_dir=artifact_dir,
    )
    rows = section.get("metric_rows", [])
    if not isinstance(rows, list):
        rows = []
    return {
        "title": _safe_str(section.get("title")) or "Реклама",
        "subtitle": _safe_str(section.get("subtitle")) or "Эффективность рекламы из advertising_efficiency artifacts.",
        "rows": rows,
        "status": _safe_str(section.get("status")) or "no_data",
        "message": _safe_str(section.get("message")),
    }


QUERY_LOSS_STATUSES = {"unprofitable", "costly"}
QUERY_WEAK_STATUSES = {"low_conversion", "low_relevance", "traffic_only", "no_orders", "insufficient_data"}
QUERY_PERFORMING_STATUSES = {"profitable", "winner"}
QUERY_GROWTH_STATUSES = {"growth_opportunity"}


def _query_status_label(value: Any) -> str:
    status = _safe_str(value).lower()
    labels = {
        "profitable": "эффективный",
        "unprofitable": "убыточный",
        "neutral": "нейтральный",
        "winner": "эффективный",
        "growth_opportunity": "гипотеза роста",
        "low_conversion": "слабая конверсия",
        "low_relevance": "низкая релевантность",
        "traffic_only": "трафик без продаж",
        "no_orders": "нет заказов",
        "costly": "дорогой запрос",
        "insufficient_data": "недостаточно данных",
        "ok": "готово",
        "partial": "частично",
        "disabled": "отключено",
        "no_data": "нет данных",
    }
    return labels.get(status, _safe_str(value) or "нет данных")


def _query_row_status(row: dict[str, Any]) -> str:
    return _safe_str(row.get("query_status") or row.get("classification") or row.get("status")).lower()


def _normalize_query_item(row: dict[str, Any], *, source: str) -> dict[str, Any]:
    query = _first_text(row.get("query"), row.get("keyword"), row.get("search_query"), row.get("phrase"))
    status = _query_row_status(row)
    return {
        "query": query,
        "sku": row.get("sku"),
        "impressions": _safe_int(row.get("impressions")),
        "clicks": _safe_int(row.get("clicks")),
        "ad_spend": _first_numeric(row, ("ad_spend", "spend", "ads_spend", "cost")),
        "orders": _safe_float(row.get("orders")),
        "buyouts": _safe_float(row.get("buyouts")),
        "revenue": _safe_float(row.get("revenue")),
        "profit": _first_numeric(row, ("profit", "net_profit")),
        "ROMI": _safe_float(row.get("ROMI") or row.get("romi")),
        "status": status,
        "status_label": _query_status_label(status),
        "recommendation": _first_text(row.get("recommendation"), row.get("recommended_action"), row.get("action")),
        "source": source,
    }


def _query_source_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        rows = _safe_dict_list(payload.get(key))
        if rows:
            return rows
    summary = _safe_dict(payload.get("summary"))
    for key in keys:
        rows = _safe_dict_list(summary.get(key))
        if rows:
            return rows
    return []


def _query_all_source_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "query_items", "queries", "query_performance"):
        rows = _safe_dict_list(payload.get(key))
        if rows:
            return rows
    return []


def _normalize_query_rows(rows: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        item = _normalize_query_item(row, source=source)
        query = _safe_str(item.get("query"))
        if not query:
            continue
        key = f"{query}|{_safe_str(item.get('sku'))}|{_safe_str(item.get('source'))}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _query_loss_key(row: dict[str, Any]) -> tuple[float, float, str]:
    profit = _safe_float(row.get("profit"))
    spend = _safe_float(row.get("ad_spend")) or 0.0
    return (profit if profit is not None else 0.0, -spend, _safe_str(row.get("query")))


def _query_value_key(row: dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        _safe_float(row.get("profit")) or 0.0,
        _safe_float(row.get("ROMI")) or 0.0,
        _safe_float(row.get("orders")) or 0.0,
        _safe_str(row.get("query")),
    )


def _query_weak_key(row: dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        _safe_float(row.get("ad_spend")) or 0.0,
        _safe_float(row.get("clicks")) or 0.0,
        _safe_float(row.get("impressions")) or 0.0,
        _safe_str(row.get("query")),
    )


def _is_loss_query(row: dict[str, Any]) -> bool:
    status = _query_row_status(row)
    profit = _safe_float(row.get("profit"))
    return status in QUERY_LOSS_STATUSES or (profit is not None and profit < 0)


def _is_weak_query(row: dict[str, Any]) -> bool:
    status = _query_row_status(row)
    if status in QUERY_WEAK_STATUSES:
        return True
    orders = _safe_float(row.get("orders"))
    has_traffic = any(_safe_float(row.get(key)) for key in ("impressions", "clicks", "ad_spend"))
    return bool(has_traffic and (orders is None or orders <= 0) and not _is_loss_query(row))


def _is_performing_query(row: dict[str, Any]) -> bool:
    status = _query_row_status(row)
    profit = _safe_float(row.get("profit"))
    return status in QUERY_PERFORMING_STATUSES or (profit is not None and profit > 0 and not _is_growth_query(row))


def _is_growth_query(row: dict[str, Any]) -> bool:
    return _query_row_status(row) in QUERY_GROWTH_STATUSES or bool(_safe_str(row.get("hypothesis")))


def _query_recommendations(
    *,
    top_loss_queries: list[dict[str, Any]],
    weak_queries: list[dict[str, Any]],
    top_performing_queries: list[dict[str, Any]],
    growth_hypotheses: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    if top_loss_queries:
        recommendations.append("Снизить ставки или остановить убыточные запросы до пересборки семантики.")
    if weak_queries:
        recommendations.append("Пересобрать слабые запросы: уточнить фразы, карточки и минус-слова.")
    if top_performing_queries or growth_hypotheses:
        recommendations.append("Перенести бюджет в эффективные запросы и проверить гипотезы роста.")
    return recommendations[:3]


def build_query_profitability_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
) -> QueryProfitabilitySectionV2:
    _ = snapshot, debug
    artifacts = _load_ads_artifacts_from_dir(artifact_dir)
    query_payload = _safe_dict(artifacts.get("query_profitability"))
    keyword_payload = _safe_dict(artifacts.get("keyword_monitoring"))
    source = "query_profitability.json" if query_payload else "missing"

    if not query_payload:
        return {
            "title": "Поисковые запросы",
            "subtitle": "Прибыльность и качество поисковых запросов.",
            "status": "no_data",
            "source": "missing",
            "message": "Данные query_profitability.json недоступны.",
            "top_loss_queries": [],
            "weak_queries": [],
            "top_performing_queries": [],
            "growth_hypotheses": [],
            "recommendations": [],
        }

    all_rows = _normalize_query_rows(_query_all_source_rows(query_payload), source=source)
    keyword_rows = _normalize_query_rows(_query_all_source_rows(keyword_payload), source="keyword_monitoring.json")
    combined_rows = all_rows or keyword_rows

    top_loss_queries = _normalize_query_rows(
        _query_source_rows(query_payload, "top_loss_queries", "top_unprofitable_queries", "loss_queries"),
        source=source,
    )
    if not top_loss_queries:
        top_loss_queries = sorted([row for row in combined_rows if _is_loss_query(row)], key=_query_loss_key)[:8]

    top_loss_keys = {_safe_str(row.get("query")) for row in top_loss_queries}
    weak_queries = _normalize_query_rows(
        _query_source_rows(query_payload, "weak_queries", "top_weak_queries"),
        source=source,
    )
    if not weak_queries:
        weak_queries = _normalize_query_rows(
            _query_source_rows(keyword_payload, "top_global_problem_queries"),
            source="keyword_monitoring.json",
        )
    if not weak_queries:
        weak_queries = sorted(
            [row for row in combined_rows if _is_weak_query(row) and _safe_str(row.get("query")) not in top_loss_keys],
            key=_query_weak_key,
            reverse=True,
        )[:8]

    top_performing_queries = _normalize_query_rows(
        _query_source_rows(query_payload, "top_performing_queries", "top_profitable_queries"),
        source=source,
    )
    if not top_performing_queries:
        top_performing_queries = sorted([row for row in combined_rows if _is_performing_query(row)], key=_query_value_key, reverse=True)[:8]

    growth_hypotheses = _normalize_query_rows(
        _query_source_rows(query_payload, "growth_hypotheses", "high_potential_queries"),
        source=source,
    )
    if not growth_hypotheses:
        growth_hypotheses = sorted([row for row in keyword_rows if _is_growth_query(row)], key=_query_value_key, reverse=True)[:5]
    if not growth_hypotheses:
        growth_hypotheses = sorted([row for row in combined_rows if _is_growth_query(row)], key=_query_value_key, reverse=True)[:5]

    raw_status = _safe_str(query_payload.get("status") or _safe_dict(query_payload.get("summary")).get("status")).lower()
    if raw_status in {"disabled", "no_data", "missing"}:
        status = raw_status
    elif not combined_rows and not any((top_loss_queries, weak_queries, top_performing_queries, growth_hypotheses)):
        status = "insufficient_data"
    elif raw_status in {"partial", "preview", "insufficient_data"}:
        status = "partial" if raw_status == "preview" else raw_status
    else:
        status = "ok"

    recommendations = [
        _safe_str(item)
        for item in _safe_list(query_payload.get("recommendations") or _safe_dict(query_payload.get("summary")).get("recommendations"))
        if _safe_str(item)
    ]
    if not recommendations:
        recommendations = _query_recommendations(
            top_loss_queries=top_loss_queries,
            weak_queries=weak_queries,
            top_performing_queries=top_performing_queries,
            growth_hypotheses=growth_hypotheses,
        )

    return {
        "title": "Поисковые запросы",
        "subtitle": "Прибыльность и качество поисковых запросов.",
        "status": status,
        "source": source,
        "message": "Поисковые запросы собраны из query_profitability.json.",
        "top_loss_queries": top_loss_queries[:8],
        "weak_queries": weak_queries[:8],
        "top_performing_queries": top_performing_queries[:8],
        "growth_hypotheses": growth_hypotheses[:5],
        "recommendations": recommendations[:3],
    }


def _load_sku_artifacts_from_dir(artifact_dir: str | Path | None) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    filenames = {
        "health_score": "health_score.json",
        "sku_watchlists": "sku_watchlists.json",
        "sku_alerts": "sku_alerts.json",
        "sku_daily_dynamics": "sku_daily_dynamics.json",
    }
    for directory in _artifact_dirs(artifact_dir):
        for key, filename in filenames.items():
            if key in loaded:
                continue
            payload = _read_json_dict(directory / filename)
            if payload:
                loaded[key] = payload
        if len(loaded) == len(filenames):
            break
    return loaded


def _first_text(*values: Any) -> str:
    for value in values:
        text = _safe_str(value)
        if text:
            return text
    return ""


def _first_list_text(value: Any) -> str:
    rows = _safe_list(value)
    for item in rows:
        text = _safe_str(item)
        if text:
            return text
    return ""


def _first_action_text(row: dict[str, Any]) -> str:
    explicit = _first_text(row.get("recommended_action"), row.get("action"), row.get("next_action"))
    if explicit:
        return explicit
    actions = _safe_list(row.get("actions"))
    for item in actions:
        if not isinstance(item, dict):
            continue
        text = _first_text(item.get("title"), item.get("recommendation"), item.get("details"))
        if text:
            return text
    alerts = _safe_list(row.get("alerts"))
    for item in alerts:
        if not isinstance(item, dict):
            continue
        status = _safe_str(item.get("status")).lower()
        if status not in {"critical", "warning"}:
            continue
        reason = _safe_str(item.get("reason"))
        if reason:
            return reason
    return ""


def _nested_numeric(row: dict[str, Any], *path: str) -> float | None:
    current: Any = row
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _safe_float(current)


def _first_sku_metric(row: dict[str, Any]) -> float | str | None:
    for key in ("metric_value", "current_value", "health_score", "attention_score", "score"):
        if key in row:
            value = row.get(key)
            numeric = _safe_float(value)
            return numeric if numeric is not None else (_safe_str(value) or None)
    for path in (
        ("metrics", "stock"),
        ("metrics", "orders"),
        ("metrics", "revenue"),
        ("metrics", "net_profit"),
        ("deltas", "orders_vs_7d_pct"),
        ("deltas", "revenue_vs_7d_pct"),
    ):
        value = _nested_numeric(row, *path)
        if value is not None:
            return value
    return None


def _normalize_sku_item(row: dict[str, Any], *, source: str, default_status: str = "") -> SkuHealthItemV2:
    sku = _first_text(row.get("sku"), row.get("nm_id"), row.get("nmId"), row.get("article"), row.get("vendor_code"))
    health_score = _safe_float(row.get("health_score"))
    attention_score = _safe_float(row.get("attention_score"))
    score = _safe_float(row.get("score"))
    if score is None:
        score = health_score if health_score is not None else attention_score
    reason = _first_text(
        row.get("reason"),
        row.get("comment"),
        row.get("message"),
        _first_list_text(row.get("reasons")),
        _first_list_text(row.get("warnings")),
    )
    if not reason:
        alerts = _safe_list(row.get("alerts"))
        for alert in alerts:
            if isinstance(alert, dict):
                reason = _safe_str(alert.get("reason"))
                if reason:
                    break
    item: SkuHealthItemV2 = {
        "sku": sku,
        "nm_id": _first_text(row.get("nm_id"), row.get("nmId")) or None,
        "article": _first_text(row.get("article"), row.get("vendor_code"), row.get("supplierArticle")) or None,
        "name": _first_text(row.get("name"), row.get("product_name"), row.get("title")) or None,
        "score": score,
        "attention_score": attention_score,
        "health_score": health_score,
        "reason": reason,
        "metric_value": _first_sku_metric(row),
        "recommended_action": _first_action_text(row),
        "status": _first_text(row.get("status"), row.get("health_status"), row.get("scoring_status"), default_status),
        "source": source,
    }
    return item


def _normalize_alert_item(row: dict[str, Any]) -> SkuHealthItemV2:
    status = "unknown"
    reason = ""
    for alert in _safe_list(row.get("alerts")):
        if not isinstance(alert, dict):
            continue
        alert_status = _safe_str(alert.get("status")).lower()
        if alert_status in {"critical", "warning"}:
            status = alert_status
            reason = _safe_str(alert.get("reason"))
            break
        if not reason:
            status = alert_status or status
            reason = _safe_str(alert.get("reason"))
    item = _normalize_sku_item(row, source="sku_alerts.json", default_status=status)
    if reason:
        item["reason"] = reason
    if not item.get("recommended_action"):
        item["recommended_action"] = reason
    item["status"] = status
    return item


def _enrich_sku_item(item: SkuHealthItemV2, context: SkuHealthItemV2 | None) -> SkuHealthItemV2:
    if not context:
        return item
    for key in ("nm_id", "article", "name", "score", "health_score", "recommended_action"):
        if item.get(key) is None or item.get(key) == "":
            value = context.get(key)
            if value is not None and value != "":
                item[key] = value  # type: ignore[literal-required]
    if not item.get("reason") and context.get("reason"):
        item["reason"] = context.get("reason", "")
    return item


def _watchlist_rows(watchlists_payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    root = _safe_dict(watchlists_payload.get("watchlists")) or watchlists_payload
    return _safe_dict_list(root.get(key))


def _count_or_none(rows: list[Any] | None, *, artifact_present: bool) -> int | None:
    if rows is None and not artifact_present:
        return None
    return len(rows or [])


def _normalize_sku_warnings(*payloads: dict[str, Any]) -> list[WarningItemV2]:
    warnings: list[WarningItemV2] = []
    for payload in payloads:
        for item in _safe_list(payload.get("warnings")):
            if isinstance(item, dict):
                message = _safe_str(item.get("message") or item.get("reason") or item.get("text"))
                if not message:
                    continue
                _append_once(
                    warnings,
                    _warning(
                        _safe_str(item.get("code")) or "sku_health_warning",
                        message,
                        block=_safe_str(item.get("block")) or "sku_health",
                        level=_safe_str(item.get("level")) or "warning",
                    ),
                )
                continue
            message = _safe_str(item)
            if message:
                _append_once(warnings, _warning("sku_health_warning", message, block="sku_health"))
    return warnings


def _sku_source_names(
    *,
    health_score: dict[str, Any],
    sku_watchlists: dict[str, Any],
    sku_alerts: dict[str, Any],
    sku_daily_dynamics: dict[str, Any],
) -> str:
    sources: list[str] = []
    if health_score:
        sources.append("health_score.json")
    if sku_watchlists:
        sources.append("sku_watchlists.json")
    if sku_alerts:
        sources.append("sku_alerts.json")
    if sku_daily_dynamics:
        sources.append("sku_daily_dynamics.json")
    return ", ".join(sources) or "missing"


def _sku_section_status(
    *,
    artifact_present: bool,
    health_score: dict[str, Any],
    sku_watchlists: dict[str, Any],
    sku_alerts: dict[str, Any],
    useful_count: int,
) -> str:
    if not artifact_present:
        return "no_data"
    if useful_count <= 0:
        return "insufficient_data"
    health_status = _safe_str(health_score.get("status") or _safe_dict(health_score.get("summary")).get("status")).lower()
    required_present = bool(health_score and sku_watchlists and sku_alerts)
    if health_status == "insufficient_data":
        return "insufficient_data"
    if health_status == "partial" or not required_present:
        return "partial"
    return "ok"


def _build_sku_summary_rows(summary: dict[str, Any], health_score: dict[str, Any]) -> list[DisplayRowV2]:
    score = _safe_dict(health_score)
    rows = [
        ("Всего SKU", summary.get("total_skus")),
        ("Здоровые SKU", summary.get("healthy_count")),
        ("SKU в росте", summary.get("growth_count")),
        ("SKU под риском", summary.get("risk_count")),
        ("Ликвидация", summary.get("liquidation_count")),
        ("Dead stock", summary.get("dead_stock_count")),
        ("Неэффективная реклама", summary.get("ad_inefficiency_count")),
        ("Падение конверсии", summary.get("conversion_drop_count")),
        ("Логистический риск", summary.get("logistics_risk_count")),
    ]
    out: list[DisplayRowV2] = []
    for label, value in rows:
        out.append(
            _display_row(
                label,
                _format_display_int(value, "шт"),
                note="SKU health / watchlists",
                status="ok" if _safe_float(value) is not None else "unavailable",
            )
        )
    out.append(
        _display_row(
            "Средний health score",
            _format_display_number(score.get("value"), digits=2),
            note=_safe_str(score.get("comment")),
            status=_safe_str(score.get("status")) or "unavailable",
        )
    )
    return out


def _sku_unique_attention_rows(*groups: list[SkuHealthItemV2], limit: int = 10) -> list[SkuHealthItemV2]:
    rows: list[SkuHealthItemV2] = []
    seen: set[str] = set()
    index: dict[str, SkuHealthItemV2] = {}
    for group in groups:
        for item in group:
            sku = _safe_str(item.get("sku"))
            key = sku or f"{item.get('source')}:{len(rows)}"
            if key in seen:
                existing = index.get(key)
                if existing is not None:
                    if not existing.get("recommended_action") and item.get("recommended_action"):
                        existing["recommended_action"] = item.get("recommended_action", "")
                    if not existing.get("reason") and item.get("reason"):
                        existing["reason"] = item.get("reason", "")
                continue
            seen.add(key)
            index[key] = item
            rows.append(item)
    rows.sort(
        key=lambda item: (
            -(_safe_float(item.get("attention_score")) or 0.0),
            _safe_float(item.get("health_score")) if _safe_float(item.get("health_score")) is not None else 9999.0,
            _safe_str(item.get("sku")),
        )
    )
    return rows[:limit]


def build_sku_health_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
) -> SkuHealthSectionV2:
    _ = debug
    safe_snapshot = _safe_dict(snapshot)
    artifacts = _load_sku_artifacts_from_dir(artifact_dir)
    health_score = _first_dict(safe_snapshot.get("health_score"), artifacts.get("health_score"))
    sku_watchlists = _first_dict(safe_snapshot.get("sku_watchlists"), artifacts.get("sku_watchlists"))
    sku_alerts = _first_dict(safe_snapshot.get("sku_alerts"), artifacts.get("sku_alerts"))
    sku_daily_dynamics = _first_dict(safe_snapshot.get("sku_daily_dynamics"), artifacts.get("sku_daily_dynamics"))

    health_summary = _safe_dict(health_score.get("summary"))
    status_counts = _safe_dict(health_summary.get("status_counts"))
    watchlists: dict[str, list[SkuHealthItemV2]] = {}
    for key in (
        "top_growth",
        "top_risk",
        "dead_stock",
        "ad_inefficiency",
        "conversion_drop",
        "logistics_risk",
    ):
        watchlists[key] = [
            _normalize_sku_item(row, source=f"sku_watchlists.json:{key}", default_status=key)
            for row in _watchlist_rows(sku_watchlists, key)
        ]

    health_items = [_normalize_sku_item(row, source="health_score.json") for row in _safe_dict_list(health_score.get("items"))]
    alert_items = [_normalize_alert_item(row) for row in _safe_dict_list(sku_alerts.get("items"))]
    health_by_sku = {_safe_str(item.get("sku")): item for item in health_items if _safe_str(item.get("sku"))}
    for group_rows in watchlists.values():
        for item in group_rows:
            _enrich_sku_item(item, health_by_sku.get(_safe_str(item.get("sku"))))
    for item in alert_items:
        _enrich_sku_item(item, health_by_sku.get(_safe_str(item.get("sku"))))
    dynamics_items = _safe_dict_list(sku_daily_dynamics.get("items"))

    total_skus = _safe_int(
        health_summary.get("total_skus")
        if health_summary.get("total_skus") is not None
        else health_summary.get("sku_count")
    )
    if total_skus is None:
        total_skus = _safe_int(sku_daily_dynamics.get("sku_count"))
    if total_skus is None and health_items:
        total_skus = len(health_items)

    healthy_count = None
    healthy = _safe_int(status_counts.get("healthy"))
    strong = _safe_int(status_counts.get("strong"))
    if healthy is not None or strong is not None:
        healthy_count = int(healthy or 0) + int(strong or 0)

    risk_count = _safe_int(status_counts.get("risk"))
    if risk_count is None and watchlists["top_risk"]:
        risk_count = len(watchlists["top_risk"])

    summary = {
        "total_skus": total_skus,
        "healthy_count": healthy_count,
        "growth_count": len(watchlists["top_growth"]) if sku_watchlists else None,
        "risk_count": risk_count,
        "liquidation_count": _safe_int(health_summary.get("LIQUIDATE")),
        "dead_stock_count": len(watchlists["dead_stock"]) if sku_watchlists else None,
        "ad_inefficiency_count": len(watchlists["ad_inefficiency"]) if sku_watchlists else None,
        "conversion_drop_count": len(watchlists["conversion_drop"]) if sku_watchlists else None,
        "logistics_risk_count": len(watchlists["logistics_risk"]) if sku_watchlists else None,
    }
    if summary["liquidation_count"] is None and watchlists["dead_stock"]:
        summary["liquidation_count"] = len(watchlists["dead_stock"])

    health_value = _safe_float(health_summary.get("average_health_score"))
    health_comment_parts = [
        f"confidence={_safe_str(health_summary.get('confidence'))}" if _safe_str(health_summary.get("confidence")) else "",
        _first_list_text(health_summary.get("reasons")),
    ]
    health_score_block = {
        "value": health_value,
        "status": _safe_str(health_score.get("status") or health_summary.get("status")) or "unavailable",
        "comment": "; ".join([part for part in health_comment_parts if part]) or "health_score artifact",
    }

    artifact_present = bool(health_score or sku_watchlists or sku_alerts or sku_daily_dynamics)
    useful_count = len(health_items) + sum(len(rows) for rows in watchlists.values()) + len(alert_items) + len(dynamics_items)
    status = _sku_section_status(
        artifact_present=artifact_present,
        health_score=health_score,
        sku_watchlists=sku_watchlists,
        sku_alerts=sku_alerts,
        useful_count=useful_count,
    )
    if status == "no_data":
        message = "SKU health artifacts отсутствуют в snapshot и artifacts."
    elif status == "insufficient_data":
        message = "SKU health artifacts найдены, но полезных SKU-данных недостаточно."
    elif status == "partial":
        message = "SKU health доступен частично; отсутствующие значения не заменялись нулями."
    else:
        message = "SKU health собран из health_score, watchlists и alerts artifacts."

    warnings = _normalize_sku_warnings(health_score, sku_watchlists, sku_alerts, sku_daily_dynamics)
    risk_rows = watchlists["top_risk"] or [
        item for item in health_items if _safe_str(item.get("status")).upper() in {"LIQUIDATE", "FIX"} or _safe_str(item.get("status")) == "risk"
    ][:10]
    growth_rows = watchlists["top_growth"] or [
        item for item in health_items if _safe_str(item.get("status")).upper() == "SCALE"
    ][:10]
    attention_rows = _sku_unique_attention_rows(
        watchlists["dead_stock"],
        watchlists["ad_inefficiency"],
        watchlists["conversion_drop"],
        watchlists["logistics_risk"],
        alert_items,
        limit=10,
    )
    daily_dynamics = {
        "date": _safe_str(sku_daily_dynamics.get("date")) or None,
        "sku_count": _safe_int(sku_daily_dynamics.get("sku_count")),
        "items_preview": dynamics_items[:10],
    } if sku_daily_dynamics else {}

    section: SkuHealthSectionV2 = {
        "title": "Состояние товаров / SKU health",
        "subtitle": "Списки SKU из health_score, sku_watchlists, sku_alerts и sku_daily_dynamics.",
        "status": status,
        "source": _sku_source_names(
            health_score=health_score,
            sku_watchlists=sku_watchlists,
            sku_alerts=sku_alerts,
            sku_daily_dynamics=sku_daily_dynamics,
        ),
        "message": message,
        "summary": summary,
        "health_score": health_score_block,
        "watchlists": watchlists,
        "alerts": alert_items,
        "daily_dynamics": daily_dynamics,
        "warnings": warnings,
        "risk_rows": risk_rows[:10],
        "growth_rows": growth_rows[:10],
        "attention_rows": attention_rows[:10],
    }
    section["summary_rows"] = _build_sku_summary_rows(summary, health_score_block)
    return section


def _load_profit_contribution_artifact(artifact_dir: str | Path | None) -> dict[str, Any]:
    for directory in _artifact_dirs(artifact_dir):
        payload = _read_json_dict(directory / "profit_contribution.json")
        if payload:
            return payload
    return {}


def _load_abc_analysis_artifact(artifact_dir: str | Path | None) -> Any:
    for directory in _artifact_dirs(artifact_dir):
        payload = _read_json_value(directory / "abc_analysis.json")
        if isinstance(payload, (dict, list)) and payload:
            return payload
    return None


def _normalize_artifact_warnings(items: Any, *, block: str, default_code: str) -> list[WarningItemV2]:
    warnings: list[WarningItemV2] = []
    for item in _safe_list(items):
        if isinstance(item, dict):
            message = _safe_str(item.get("message") or item.get("text") or item.get("reason") or item.get("code"))
            if not message:
                continue
            _append_once(
                warnings,
                _warning(
                    _safe_str(item.get("code")) or default_code,
                    message,
                    block=_safe_str(item.get("block") or item.get("source")) or block,
                    level=_safe_str(item.get("level") or item.get("severity")) or "warning",
                ),
            )
            continue
        message = _safe_str(item)
        if message:
            _append_once(warnings, _warning(default_code, message, block=block))
    return warnings


def _sum_present_numeric(rows: list[dict[str, Any]], field_name: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        if field_name not in row:
            continue
        value = _safe_float(row.get(field_name))
        if value is None:
            continue
        total += value
        seen = True
    return round(total, 6) if seen else None


def _sku_action_index_from_health(sku_health_section: dict[str, Any] | None) -> dict[str, str]:
    section = _safe_dict(sku_health_section)
    watchlists = _safe_dict(section.get("watchlists"))
    indexed: dict[str, str] = {}
    for key in ("top_risk", "top_growth"):
        for row in _safe_dict_list(watchlists.get(key)):
            sku = _first_text(row.get("sku"), row.get("nm_id"), row.get("nmId"), row.get("article"))
            action = _first_text(row.get("recommended_action"), row.get("reason"))
            if sku and action and sku not in indexed:
                indexed[sku] = action
    return indexed


def _profit_row_source(row: dict[str, Any], default_source: str) -> str:
    return _first_text(row.get("source"), row.get("artifact_source"), default_source) or default_source


def _normalize_profit_sku_item(
    row: dict[str, Any],
    *,
    source: str,
    actions_by_sku: dict[str, str],
) -> ProfitSkuItemV2:
    sku = _first_text(row.get("sku"), row.get("nm_id"), row.get("nmId"), row.get("article"), row.get("vendor_code"))
    nm_id = _first_text(row.get("nm_id"), row.get("nmId"))
    action = _first_text(row.get("recommended_action"), row.get("action"), row.get("next_action"))
    if not action and sku:
        action = actions_by_sku.get(sku, "")

    item: ProfitSkuItemV2 = {
        "sku": sku,
        "nm_id": nm_id or None,
        "name": _first_text(row.get("name"), row.get("product_name"), row.get("title")) or None,
        "revenue": _first_numeric(row, ("revenue", "revenue_total", "buyouts_amount", "orders_amount", "sales_amount")),
        "profit": _first_numeric(row, ("profit", "net_profit", "total_profit")),
        "profit_margin": _first_numeric(row, ("profit_margin", "margin_pct", "margin")),
        "contribution_share": _first_numeric(row, ("contribution_share", "profit_share", "share")),
        "status": _first_text(row.get("status"), row.get("profit_group"), row.get("class")) or "unknown",
        "recommended_action": action,
        "source": _profit_row_source(row, source),
    }
    return item


def _profit_source_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        rows = _safe_dict_list(payload.get(key))
        if rows:
            return rows
    summary = _safe_dict(payload.get("summary"))
    for key in keys:
        rows = _safe_dict_list(summary.get(key))
        if rows:
            return rows
    return []


def _profit_all_source_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _profit_source_rows(payload, "sku_pnl", "items")
    if rows:
        return rows

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("p1", "p2", "p3", "p4"):
        for row in _safe_dict_list(payload.get(key)):
            sku = _first_text(row.get("sku"), row.get("nm_id"), row.get("nmId"))
            dedupe_key = sku or f"{key}:{len(combined)}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            combined.append(row)
    return combined


def _derive_profit_top_rows(rows: list[ProfitSkuItemV2], *, limit: int = 10) -> list[ProfitSkuItemV2]:
    candidates = [row for row in rows if _safe_float(row.get("profit")) is not None]
    candidates.sort(key=lambda row: (_safe_float(row.get("profit")) or float("-inf"), _safe_str(row.get("sku"))), reverse=True)
    return candidates[:limit]


def _derive_profit_loss_rows(rows: list[ProfitSkuItemV2], *, limit: int = 10) -> list[ProfitSkuItemV2]:
    candidates = [row for row in rows if (_safe_float(row.get("profit")) is not None and (_safe_float(row.get("profit")) or 0.0) < 0)]
    candidates.sort(key=lambda row: (_safe_float(row.get("profit")) or 0.0, _safe_str(row.get("sku"))))
    return candidates[:limit]


def _profit_status(
    *,
    artifact_present: bool,
    raw_status: str,
    rows: list[ProfitSkuItemV2],
    summary: dict[str, Any],
) -> str:
    if not artifact_present:
        return "no_data"
    if raw_status in {"no_data", "missing"}:
        return "no_data"
    if raw_status and raw_status not in {"ok", "success"}:
        return "partial"
    if not rows and all(_safe_float(summary.get(key)) is None for key in ("total_profit", "total_revenue", "top_sku_share")):
        return "partial"
    for row in rows:
        if _safe_float(row.get("profit")) is None or _safe_float(row.get("revenue")) is None:
            return "partial"
    return "ok"


def _build_profit_summary_rows(summary: dict[str, Any]) -> list[DisplayRowV2]:
    return [
        _display_row(
            "Общая прибыль",
            _format_display_money(summary.get("total_profit")),
            note="profit_contribution.json",
            status="ok" if _safe_float(summary.get("total_profit")) is not None else "unavailable",
        ),
        _display_row(
            "Общая выручка",
            _format_display_money(summary.get("total_revenue")),
            note="profit_contribution.json",
            status="ok" if _safe_float(summary.get("total_revenue")) is not None else "unavailable",
        ),
        _display_row(
            "Доля топ SKU",
            _format_display_share_percent(summary.get("top_sku_share")),
            note="profit contribution share",
            status="ok" if _safe_float(summary.get("top_sku_share")) is not None else "unavailable",
        ),
        _display_row(
            "Убыточные SKU",
            _format_display_int(summary.get("loss_sku_count"), "шт"),
            note="profit_contribution.json",
            status="ok" if _safe_float(summary.get("loss_sku_count")) is not None else "unavailable",
        ),
    ]


def build_profit_contribution_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
    sku_health_section: dict[str, Any] | None = None,
) -> ProfitContributionSectionV2:
    _ = snapshot, debug
    payload = _load_profit_contribution_artifact(artifact_dir)
    source = "profit_contribution.json" if payload else "missing"
    if not payload:
        summary = {
            "total_profit": None,
            "total_revenue": None,
            "top_sku_share": None,
            "loss_sku_count": None,
        }
        section: ProfitContributionSectionV2 = {
            "title": "Прибыль по товарам",
            "subtitle": "Вклад SKU в прибыль по artifact profit_contribution.json.",
            "status": "no_data",
            "source": "missing",
            "message": "Данные profit_contribution.json недоступны.",
            "summary": summary,
            "top_profit_skus": [],
            "loss_skus": [],
            "sku_pnl": [],
            "warnings": [],
        }
        section["summary_rows"] = _build_profit_summary_rows(summary)
        return section

    actions_by_sku = _sku_action_index_from_health(sku_health_section)
    all_rows = [
        _normalize_profit_sku_item(row, source=source, actions_by_sku=actions_by_sku)
        for row in _profit_all_source_rows(payload)
    ]
    top_profit_skus = [
        _normalize_profit_sku_item(row, source=source, actions_by_sku=actions_by_sku)
        for row in _profit_source_rows(payload, "top_profit_skus", "top_profit_sku")
    ]
    if not top_profit_skus and all_rows:
        top_profit_skus = _derive_profit_top_rows(all_rows)

    loss_skus = [
        _normalize_profit_sku_item(row, source=source, actions_by_sku=actions_by_sku)
        for row in _profit_source_rows(payload, "loss_skus", "top_loss_skus", "top_loss_sku")
    ]
    if not loss_skus:
        p4_rows = [
            _normalize_profit_sku_item(row, source=source, actions_by_sku=actions_by_sku)
            for row in _safe_dict_list(payload.get("p4"))
        ]
        loss_skus = p4_rows or _derive_profit_loss_rows(all_rows)

    summary_payload = _safe_dict(payload.get("summary"))
    meta_payload = _safe_dict(payload.get("meta"))
    total_profit = _pick_numeric(
        (summary_payload, ("total_profit", "profit")),
        (meta_payload, ("total_profit", "profit")),
        (payload, ("total_profit", "profit")),
    )
    if total_profit is None:
        total_profit = _sum_present_numeric(all_rows, "profit")
    total_revenue = _pick_numeric(
        (summary_payload, ("total_revenue", "revenue")),
        (meta_payload, ("total_revenue", "revenue")),
        (payload, ("total_revenue", "revenue")),
    )
    if total_revenue is None:
        total_revenue = _sum_present_numeric(all_rows, "revenue")

    top_sku_share = _pick_numeric(
        (summary_payload, ("top_sku_share", "top_profit_share", "top_20_profit_share")),
        (meta_payload, ("top_sku_share", "top_profit_share", "top_20_profit_share")),
        (payload, ("top_sku_share", "top_profit_share", "top_20_profit_share")),
    )
    if top_sku_share is None:
        top_sku_share = _sum_present_numeric(top_profit_skus, "contribution_share")
    loss_sku_count = _safe_int(
        _pick_numeric(
            (summary_payload, ("loss_sku_count", "loss_count")),
            (meta_payload, ("loss_sku_count", "loss_count")),
            (payload, ("loss_sku_count", "loss_count")),
        )
    )
    if loss_sku_count is None and loss_skus:
        loss_sku_count = len(loss_skus)
    elif loss_sku_count is None and all_rows:
        derived_losses = [row for row in all_rows if (_safe_float(row.get("profit")) is not None and (_safe_float(row.get("profit")) or 0.0) < 0)]
        known_profit_rows = [row for row in all_rows if _safe_float(row.get("profit")) is not None]
        loss_sku_count = len(derived_losses) if derived_losses or len(known_profit_rows) == len(all_rows) else None

    summary = {
        "total_profit": total_profit,
        "total_revenue": total_revenue,
        "top_sku_share": top_sku_share,
        "loss_sku_count": loss_sku_count,
    }
    warnings = _normalize_artifact_warnings(payload.get("warnings"), block="profit_contribution", default_code="profit_contribution_warning")
    raw_status = _safe_str(payload.get("status") or summary_payload.get("status")).lower()
    status = _profit_status(artifact_present=True, raw_status=raw_status, rows=all_rows, summary=summary)
    if status == "no_data":
        message = "Данные profit_contribution.json недоступны."
    elif status == "partial":
        message = "Profit contribution доступен частично; пропуски не заменялись нулями."
    else:
        message = "Profit contribution собран из artifact profit_contribution.json."

    section = {
        "title": "Прибыль по товарам",
        "subtitle": "Вклад SKU в прибыль по artifact profit_contribution.json.",
        "status": status,
        "source": source,
        "message": message,
        "summary": summary,
        "top_profit_skus": top_profit_skus[:10],
        "loss_skus": loss_skus[:10],
        "sku_pnl": all_rows,
        "warnings": warnings,
    }
    section["summary_rows"] = _build_profit_summary_rows(summary)
    return section


def _abc_category_value(row: dict[str, Any]) -> str:
    return _first_text(row.get("category"), row.get("abc_class"), row.get("class")).upper()


def _normalize_abc_item(row: dict[str, Any], *, category: str = "") -> AbcSkuItemV2:
    resolved_category = _abc_category_value(row) or _safe_str(category).upper()
    metric_value = _first_numeric(row, ("metric_value", "profit", "revenue"))
    sku = _first_text(row.get("sku"), row.get("nm_id"), row.get("nmId"), row.get("article"), row.get("vendor_code"))
    return {
        "sku": sku,
        "nm_id": _first_text(row.get("nm_id"), row.get("nmId")) or None,
        "name": _first_text(row.get("name"), row.get("product_name"), row.get("title")) or None,
        "category": resolved_category,
        "metric_value": metric_value,
        "cumulative_share": _first_numeric(row, ("cumulative_share", "cumulative_profit_share")),
        "status": _first_text(row.get("status")) or "ok",
    }


def _abc_rows_from_payload(payload: Any) -> list[AbcSkuItemV2]:
    if isinstance(payload, list):
        return [_normalize_abc_item(row) for row in _safe_dict_list(payload)]
    if not isinstance(payload, dict):
        return []
    rows: list[AbcSkuItemV2] = []
    direct_rows = _safe_dict_list(payload.get("items"))
    if direct_rows:
        return [_normalize_abc_item(row) for row in direct_rows]
    for category in ("A", "B", "C"):
        for row in _safe_dict_list(payload.get(category)):
            rows.append(_normalize_abc_item(row, category=category))
    return rows


def _abc_categories(rows: list[AbcSkuItemV2]) -> dict[str, list[AbcSkuItemV2]]:
    categories: dict[str, list[AbcSkuItemV2]] = {"A": [], "B": [], "C": []}
    for row in rows:
        category = _safe_str(row.get("category")).upper()
        if category not in categories:
            continue
        categories[category].append(row)
    return categories


def _abc_share_from_rows(rows: list[dict[str, Any]], category: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        if _abc_category_value(row) != category:
            continue
        value = _first_numeric(row, ("category_share", "profit_share", "share", "contribution_share"))
        if value is None:
            continue
        total += value
        seen = True
    return round(total, 6) if seen else None


def _abc_raw_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _safe_dict_list(payload)
    if not isinstance(payload, dict):
        return []
    rows = _safe_dict_list(payload.get("items"))
    if rows:
        return rows
    out: list[dict[str, Any]] = []
    for category in ("A", "B", "C"):
        for row in _safe_dict_list(payload.get(category)):
            item = dict(row)
            item.setdefault("category", category)
            out.append(item)
    return out


def _abc_summary_from_payload(payload: Any, rows: list[AbcSkuItemV2]) -> dict[str, Any]:
    root = _safe_dict(payload)
    summary_payload = _safe_dict(root.get("summary"))
    categories = _abc_categories(rows)
    raw_rows = _abc_raw_rows(payload)

    total_skus = _safe_int(
        _pick_numeric((summary_payload, ("total_skus", "sku_count")), (root, ("total_skus", "sku_count")))
    )
    if total_skus is None and rows:
        total_skus = len(rows)

    summary = {
        "total_skus": total_skus,
        "category_A_count": _safe_int(_pick_numeric((summary_payload, ("category_A_count", "A_count")), (root, ("category_A_count", "A_count")))),
        "category_B_count": _safe_int(_pick_numeric((summary_payload, ("category_B_count", "B_count")), (root, ("category_B_count", "B_count")))),
        "category_C_count": _safe_int(_pick_numeric((summary_payload, ("category_C_count", "C_count")), (root, ("category_C_count", "C_count")))),
        "category_A_share": _pick_numeric((summary_payload, ("category_A_share", "A_share")), (root, ("category_A_share", "A_share"))),
        "category_B_share": _pick_numeric((summary_payload, ("category_B_share", "B_share")), (root, ("category_B_share", "B_share"))),
        "category_C_share": _pick_numeric((summary_payload, ("category_C_share", "C_share")), (root, ("category_C_share", "C_share"))),
    }
    for category in ("A", "B", "C"):
        count_key = f"category_{category}_count"
        if summary[count_key] is None and rows:
            summary[count_key] = len(categories[category])
        share_key = f"category_{category}_share"
        if summary[share_key] is None and raw_rows:
            summary[share_key] = _abc_share_from_rows(raw_rows, category)
    return summary


def _abc_status(*, artifact_present: bool, raw_status: str, rows: list[AbcSkuItemV2], summary: dict[str, Any]) -> str:
    if not artifact_present:
        return "no_data"
    if raw_status in {"no_data", "missing"}:
        return "no_data"
    if raw_status and raw_status not in {"ok", "success"}:
        return "partial"
    if not rows and _safe_float(summary.get("total_skus")) is None:
        return "partial"
    for row in rows:
        if not _safe_str(row.get("category")) or _safe_float(row.get("metric_value")) is None:
            return "partial"
    return "ok"


def _build_abc_summary_rows(summary: dict[str, Any]) -> list[DisplayRowV2]:
    return [
        _display_row(
            "Всего SKU",
            _format_display_int(summary.get("total_skus"), "шт"),
            note="abc_analysis.json",
            status="ok" if _safe_float(summary.get("total_skus")) is not None else "unavailable",
        ),
        _display_row(
            "Категория A",
            f"{_format_display_int(summary.get('category_A_count'), 'шт')} / {_format_display_share_percent(summary.get('category_A_share'))}",
            note="ABC share",
            status="ok" if _safe_float(summary.get("category_A_count")) is not None else "unavailable",
        ),
        _display_row(
            "Категория B",
            f"{_format_display_int(summary.get('category_B_count'), 'шт')} / {_format_display_share_percent(summary.get('category_B_share'))}",
            note="ABC share",
            status="ok" if _safe_float(summary.get("category_B_count")) is not None else "unavailable",
        ),
        _display_row(
            "Категория C",
            f"{_format_display_int(summary.get('category_C_count'), 'шт')} / {_format_display_share_percent(summary.get('category_C_share'))}",
            note="ABC share",
            status="ok" if _safe_float(summary.get("category_C_count")) is not None else "unavailable",
        ),
    ]


def _build_abc_section_summary_rows(summary: dict[str, Any]) -> list[DisplayRowV2]:
    rows = _build_abc_summary_rows(summary)
    rows.extend(
        [
            _display_row(
                "Критичные A-SKU",
                _format_display_int(summary.get("critical_a_skus_count"), "шт"),
                note="A-SKU с риском маржи или прибыли",
                status="ok" if _safe_float(summary.get("critical_a_skus_count")) is not None else "unavailable",
            ),
            _display_row(
                "C-SKU с рекламой",
                _format_display_int(summary.get("c_skus_with_ads_count"), "шт"),
                note="C-категория с рекламным расходом",
                status="ok" if _safe_float(summary.get("c_skus_with_ads_count")) is not None else "unavailable",
            ),
            _display_row(
                "Низкая маржинальность",
                _format_display_int(summary.get("low_margin_skus_count"), "шт"),
                note="SKU с низкой или отрицательной маржой",
                status="ok" if _safe_float(summary.get("low_margin_skus_count")) is not None else "unavailable",
            ),
        ]
    )
    return rows


def _sku_lookup_key(row: dict[str, Any]) -> str:
    return _first_text(row.get("sku"), row.get("nm_id"), row.get("nmId"), row.get("article"), row.get("vendor_code"))


def _merge_sku_index_row(index: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    sku = _sku_lookup_key(row)
    if not sku:
        return
    target = index.setdefault(sku, {})
    for key, value in row.items():
        if key not in target or target.get(key) in (None, ""):
            target[key] = value


def _profit_sku_index(
    *,
    artifact_dir: str | Path | None,
    profit_contribution_section: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    section = _safe_dict(profit_contribution_section)
    for key in ("sku_pnl", "top_profit_skus", "loss_skus"):
        for row in _safe_dict_list(section.get(key)):
            _merge_sku_index_row(index, row)

    payload = _load_profit_contribution_artifact(artifact_dir)
    for row in _profit_all_source_rows(payload):
        _merge_sku_index_row(index, row)
    for key in ("top_profit_skus", "top_profit_sku", "loss_skus", "top_loss_skus", "top_loss_sku"):
        for row in _profit_source_rows(payload, key):
            _merge_sku_index_row(index, row)
    return index


def _abc_ad_spend_index(snapshot: dict[str, Any], artifact_dir: str | Path | None) -> dict[str, float]:
    artifacts = _load_ads_artifacts_from_dir(artifact_dir)
    source_blocks = [
        _safe_dict(snapshot).get("advertising_efficiency"),
        _safe_dict(snapshot).get("advertising_efficiency_daily"),
        artifacts.get("advertising_efficiency"),
    ]
    row_keys = (
        "sku_performance",
        "sku_performance_rows",
        "sku_rows",
        "skus",
        "items",
        "campaign_skus",
        "campaign_sku_performance",
    )
    index: dict[str, float] = {}
    for block in source_blocks:
        if not isinstance(block, dict):
            continue
        rows: list[dict[str, Any]] = []
        for key in row_keys:
            rows.extend(_safe_dict_list(block.get(key)))
        for row in rows:
            sku = _sku_lookup_key(row)
            spend = _first_numeric(row, ("ad_spend", "ads_spend", "spend", "total_ad_spend", "cost"))
            if not sku or spend is None:
                continue
            index[sku] = round(index.get(sku, 0.0) + spend, 6)
    return index


def _abc_section_source_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    root = _safe_dict(payload)
    for key in keys:
        rows = _safe_dict_list(root.get(key))
        if rows:
            return rows
    summary = _safe_dict(root.get("summary"))
    for key in keys:
        rows = _safe_dict_list(summary.get(key))
        if rows:
            return rows
    return []


def _normalize_abc_section_sku(
    row: dict[str, Any],
    *,
    category: str = "",
    profit_by_sku: dict[str, dict[str, Any]],
    ad_spend_by_sku: dict[str, float],
    reason: str = "",
    recommended_action: str = "",
) -> AbcSectionSkuItemV2:
    sku = _sku_lookup_key(row)
    fallback = profit_by_sku.get(sku, {})
    abc_class = _abc_category_value(row) or _safe_str(category).upper()
    revenue = _first_numeric(row, ("revenue", "total_revenue", "sales", "sales_amount"))
    if revenue is None:
        revenue = _first_numeric(fallback, ("revenue", "total_revenue", "sales", "sales_amount"))
    profit = _first_numeric(row, ("profit", "gross_profit", "net_profit"))
    if profit is None:
        profit = _first_numeric(fallback, ("profit", "gross_profit", "net_profit"))
    profit_margin = _first_numeric(row, ("profit_margin", "margin", "margin_rate", "profitability"))
    if profit_margin is None:
        profit_margin = _first_numeric(fallback, ("profit_margin", "margin", "margin_rate", "profitability"))
    if profit_margin is None and profit is not None and revenue not in (None, 0):
        profit_margin = round(profit / revenue, 6)
    ad_spend = _first_numeric(row, ("ad_spend", "ads_spend", "spend", "total_ad_spend", "cost"))
    if ad_spend is None:
        ad_spend = ad_spend_by_sku.get(sku)

    return {
        "sku": sku,
        "nm_id": _first_text(row.get("nm_id"), row.get("nmId"), fallback.get("nm_id"), fallback.get("nmId")) or None,
        "name": _first_text(
            row.get("name"),
            row.get("product_name"),
            row.get("title"),
            fallback.get("name"),
            fallback.get("product_name"),
            fallback.get("title"),
        )
        or None,
        "abc_class": abc_class,
        "revenue": revenue,
        "profit": profit,
        "profit_margin": profit_margin,
        "ad_spend": ad_spend,
        "reason": _first_text(row.get("reason"), row.get("comment"), reason),
        "recommended_action": _first_text(row.get("recommended_action"), row.get("action"), recommended_action),
        "source": _first_text(row.get("source"), "abc_analysis.json") or "abc_analysis.json",
    }


def _abc_section_rows_from_payload(
    payload: Any,
    *,
    profit_by_sku: dict[str, dict[str, Any]],
    ad_spend_by_sku: dict[str, float],
) -> list[AbcSectionSkuItemV2]:
    rows = _abc_raw_rows(payload)
    return [
        _normalize_abc_section_sku(row, profit_by_sku=profit_by_sku, ad_spend_by_sku=ad_spend_by_sku)
        for row in rows
    ]


def _abc_margin_is_low(value: Any) -> bool:
    margin = _safe_float(value)
    if margin is None:
        return False
    threshold = 10.0 if abs(margin) > 1.0 else 0.10
    return margin <= threshold


def _abc_section_sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    revenue = _safe_float(row.get("revenue")) or 0.0
    profit = _safe_float(row.get("profit")) or 0.0
    ad_spend = _safe_float(row.get("ad_spend")) or 0.0
    return (revenue, profit, ad_spend)


def _is_critical_a_sku(row: dict[str, Any]) -> bool:
    if _safe_str(row.get("abc_class")).upper() != "A":
        return False
    status = _safe_str(row.get("status")).lower()
    reason = _safe_str(row.get("reason")).lower()
    profit = _safe_float(row.get("profit"))
    return (
        status in {"critical", "risk", "warning"}
        or "risk" in reason
        or "крит" in reason
        or (profit is not None and profit < 0)
        or _abc_margin_is_low(row.get("profit_margin"))
    )


def _is_low_margin_sku(row: dict[str, Any]) -> bool:
    profit = _safe_float(row.get("profit"))
    return (profit is not None and profit < 0) or _abc_margin_is_low(row.get("profit_margin"))


def _abc_with_reason_action(
    row: AbcSectionSkuItemV2,
    *,
    reason: str,
    recommended_action: str,
) -> AbcSectionSkuItemV2:
    item: AbcSectionSkuItemV2 = dict(row)
    if not _safe_str(item.get("reason")):
        item["reason"] = reason
    if not _safe_str(item.get("recommended_action")):
        item["recommended_action"] = recommended_action
    return item


def _abc_section_recommendations(
    payload: Any,
    *,
    critical_a_skus: list[AbcSectionSkuItemV2],
    c_skus_with_ads: list[AbcSectionSkuItemV2],
    low_margin_skus: list[AbcSectionSkuItemV2],
) -> list[str]:
    root = _safe_dict(payload)
    recommendations: list[str] = []
    def append_text_once(text: str) -> None:
        if text and text not in recommendations:
            recommendations.append(text)

    for item in _safe_list(root.get("recommendations") or root.get("actions")):
        text = _safe_str(item.get("text") if isinstance(item, dict) else item)
        if text:
            append_text_once(text)

    if critical_a_skus:
        append_text_once("Проверить наличие, цену и маржу критичных A-SKU.")
    if c_skus_with_ads:
        append_text_once("Снизить или остановить рекламу C-SKU без достаточного вклада.")
    if low_margin_skus:
        append_text_once("Пересчитать цену, скидки и себестоимость SKU с низкой маржинальностью.")
    return recommendations[:5]


def _abc_section_status(
    *,
    artifact_present: bool,
    raw_status: str,
    rows: list[AbcSectionSkuItemV2],
    summary: dict[str, Any],
) -> str:
    if not artifact_present:
        return "no_data"
    if raw_status in {"no_data", "missing"}:
        return "no_data"
    if raw_status and raw_status not in {"ok", "success"}:
        return "partial"
    if not rows and _safe_float(summary.get("total_skus")) is None:
        return "partial"
    if any(not _safe_str(row.get("sku")) or not _safe_str(row.get("abc_class")) for row in rows):
        return "partial"
    if rows and all(_safe_float(row.get("revenue")) is None and _safe_float(row.get("profit")) is None for row in rows):
        return "partial"
    return "ok"


def build_abc_analysis_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
) -> AbcAnalysisSectionV2:
    _ = snapshot, debug
    payload = _load_abc_analysis_artifact(artifact_dir)
    source = "abc_analysis.json" if payload else "missing"
    if payload is None:
        summary = {
            "total_skus": None,
            "category_A_count": None,
            "category_B_count": None,
            "category_C_count": None,
            "category_A_share": None,
            "category_B_share": None,
            "category_C_share": None,
        }
        section: AbcAnalysisSectionV2 = {
            "title": "ABC-анализ",
            "subtitle": "ABC-категории SKU по artifact abc_analysis.json.",
            "status": "no_data",
            "source": "missing",
            "message": "Данные abc_analysis.json недоступны.",
            "summary": summary,
            "categories": {"A": [], "B": [], "C": []},
            "warnings": [],
        }
        section["summary_rows"] = _build_abc_summary_rows(summary)
        return section

    rows = _abc_rows_from_payload(payload)
    categories = _abc_categories(rows)
    summary = _abc_summary_from_payload(payload, rows)
    root = _safe_dict(payload)
    warnings = _normalize_artifact_warnings(root.get("warnings"), block="abc_analysis", default_code="abc_analysis_warning")
    if _safe_str(root.get("abc_message")):
        _append_once(warnings, _warning("abc_message", _safe_str(root.get("abc_message")), block="abc_analysis", level="info"))
    raw_status = _safe_str(root.get("status") or _safe_dict(root.get("summary")).get("status")).lower()
    status = _abc_status(artifact_present=True, raw_status=raw_status, rows=rows, summary=summary)
    if status == "no_data":
        message = "Данные abc_analysis.json недоступны."
    elif status == "partial":
        message = "ABC-анализ доступен частично; пропуски не заменялись нулями."
    else:
        message = "ABC-анализ собран из artifact abc_analysis.json."

    section = {
        "title": "ABC-анализ",
        "subtitle": "ABC-категории SKU по artifact abc_analysis.json.",
        "status": status,
        "source": source,
        "message": message,
        "summary": summary,
        "categories": categories,
        "warnings": warnings,
    }
    section["summary_rows"] = _build_abc_summary_rows(summary)
    return section


def build_abc_section_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    artifact_dir: str | Path | None = None,
    profit_contribution_section: dict[str, Any] | None = None,
) -> AbcSectionV2:
    _ = debug
    payload = _load_abc_analysis_artifact(artifact_dir)
    if payload is None:
        summary = {
            "total_skus": None,
            "category_A_count": None,
            "category_B_count": None,
            "category_C_count": None,
            "category_A_share": None,
            "category_B_share": None,
            "category_C_share": None,
            "critical_a_skus_count": None,
            "c_skus_with_ads_count": None,
            "low_margin_skus_count": None,
        }
        section: AbcSectionV2 = {
            "title": "Ассортимент / ABC",
            "subtitle": "ABC-анализ SKU по artifact abc_analysis.json.",
            "status": "no_data",
            "source": "missing",
            "message": "Данные abc_analysis.json недоступны.",
            "summary": summary,
            "top_a_skus": [],
            "critical_a_skus": [],
            "c_skus_with_ads": [],
            "low_margin_skus": [],
            "recommendations": [],
            "warnings": [],
        }
        section["summary_rows"] = _build_abc_section_summary_rows(summary)
        return section

    profit_by_sku = _profit_sku_index(
        artifact_dir=artifact_dir,
        profit_contribution_section=profit_contribution_section,
    )
    ad_spend_by_sku = _abc_ad_spend_index(snapshot, artifact_dir)
    all_rows = _abc_section_rows_from_payload(
        payload,
        profit_by_sku=profit_by_sku,
        ad_spend_by_sku=ad_spend_by_sku,
    )
    summary_rows_source = _abc_rows_from_payload(payload)

    explicit_top_a = _abc_section_source_rows(payload, "top_a_skus", "top_A_skus", "a_skus")
    top_a_skus = [
        _normalize_abc_section_sku(
            row,
            category="A",
            profit_by_sku=profit_by_sku,
            ad_spend_by_sku=ad_spend_by_sku,
            reason="основной вклад в оборот или прибыль",
            recommended_action="держать в наличии и защищать маржу",
        )
        for row in explicit_top_a
    ]
    if not top_a_skus:
        top_a_skus = [
            _abc_with_reason_action(
                row,
                reason="основной вклад в оборот или прибыль",
                recommended_action="держать в наличии и защищать маржу",
            )
            for row in sorted(
                [row for row in all_rows if _safe_str(row.get("abc_class")).upper() == "A"],
                key=_abc_section_sort_key,
                reverse=True,
            )
        ]

    explicit_critical = _abc_section_source_rows(payload, "critical_a_skus", "critical_A_skus", "risk_a_skus")
    critical_a_skus = [
        _normalize_abc_section_sku(
            row,
            category="A",
            profit_by_sku=profit_by_sku,
            ad_spend_by_sku=ad_spend_by_sku,
            reason="критичный A-SKU",
            recommended_action="проверить остатки, цену и маржу",
        )
        for row in explicit_critical
    ]
    if not critical_a_skus:
        critical_a_skus = [
            _abc_with_reason_action(
                row,
                reason="A-SKU с риском маржи или прибыли",
                recommended_action="проверить остатки, цену и маржу",
            )
            for row in all_rows
            if _is_critical_a_sku(row)
        ]

    explicit_c_ads = _abc_section_source_rows(payload, "c_skus_with_ads", "C_skus_with_ads", "c_ads_skus")
    c_skus_with_ads = [
        _normalize_abc_section_sku(
            row,
            category="C",
            profit_by_sku=profit_by_sku,
            ad_spend_by_sku=ad_spend_by_sku,
            reason="C-SKU с рекламной активностью",
            recommended_action="проверить окупаемость рекламы",
        )
        for row in explicit_c_ads
    ]
    if not c_skus_with_ads:
        c_skus_with_ads = [
            _abc_with_reason_action(
                row,
                reason="C-SKU с рекламной активностью",
                recommended_action="проверить окупаемость рекламы",
            )
            for row in all_rows
            if _safe_str(row.get("abc_class")).upper() == "C" and (_safe_float(row.get("ad_spend")) or 0.0) > 0
        ]

    explicit_low_margin = _abc_section_source_rows(payload, "low_margin_skus", "low_margin_items")
    low_margin_skus = [
        _normalize_abc_section_sku(
            row,
            profit_by_sku=profit_by_sku,
            ad_spend_by_sku=ad_spend_by_sku,
            reason="низкая маржинальность",
            recommended_action="пересчитать цену, скидки и себестоимость",
        )
        for row in explicit_low_margin
    ]
    if not low_margin_skus:
        low_margin_skus = [
            _abc_with_reason_action(
                row,
                reason="низкая маржинальность",
                recommended_action="пересчитать цену, скидки и себестоимость",
            )
            for row in all_rows
            if _is_low_margin_sku(row)
        ]

    summary = _abc_summary_from_payload(payload, summary_rows_source)
    summary["critical_a_skus_count"] = len(critical_a_skus) if all_rows or critical_a_skus else None
    summary["c_skus_with_ads_count"] = len(c_skus_with_ads) if all_rows or c_skus_with_ads else None
    summary["low_margin_skus_count"] = len(low_margin_skus) if all_rows or low_margin_skus else None

    root = _safe_dict(payload)
    warnings = _normalize_artifact_warnings(root.get("warnings"), block="abc_analysis", default_code="abc_analysis_warning")
    raw_status = _safe_str(root.get("status") or _safe_dict(root.get("summary")).get("status")).lower()
    status = _abc_section_status(artifact_present=True, raw_status=raw_status, rows=all_rows, summary=summary)
    if status == "no_data":
        message = "Данные abc_analysis.json недоступны."
    elif status == "partial":
        message = "ABC-анализ доступен частично; пропуски не заменялись нулями."
    else:
        message = "ABC-анализ собран из artifact abc_analysis.json."

    section: AbcSectionV2 = {
        "title": "Ассортимент / ABC",
        "subtitle": "Вклад SKU, критичные A-SKU и рекламная активность C-SKU.",
        "status": status,
        "source": "abc_analysis.json",
        "message": message,
        "summary": summary,
        "top_a_skus": top_a_skus[:10],
        "critical_a_skus": critical_a_skus[:10],
        "c_skus_with_ads": c_skus_with_ads[:10],
        "low_margin_skus": low_margin_skus[:10],
        "recommendations": _abc_section_recommendations(
            payload,
            critical_a_skus=critical_a_skus,
            c_skus_with_ads=c_skus_with_ads,
            low_margin_skus=low_margin_skus,
        ),
        "warnings": warnings,
    }
    section["summary_rows"] = _build_abc_section_summary_rows(summary)
    return section


def build_finance_section_v2(finance_final: dict[str, Any]) -> SectionV2:
    finance = _safe_dict(finance_final)
    available = bool(finance.get("available", False))
    finance_status = _safe_str(finance.get("status")) or ("ok" if available else "unavailable")
    section_status = "warning" if finance_status == "lagged" else ("ok" if finance_status == "ok" else "unavailable")
    row_warning = finance_status == "lagged"
    source = _format_display_text(finance.get("source"))
    target_date = _format_display_text(finance.get("target_date"))
    actual_date = _format_display_text(finance.get("actual_date"))

    rows: list[DisplayRowV2] = [
        _display_row(
            "Статус",
            _format_display_text(finance_status),
            note=f"Операционный день: {target_date}; финансы: {actual_date}",
            status=section_status,
        ),
        _display_row(
            "Валовая выручка",
            _format_display_money(finance.get("gross_revenue")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("gross_revenue"), warning=row_warning),
        ),
        _display_row(
            "К перечислению продавцу",
            _format_display_money(finance.get("seller_payout")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("seller_payout"), warning=row_warning),
        ),
        _display_row(
            "Комиссия WB",
            _format_display_money(finance.get("wb_commission")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("wb_commission"), warning=row_warning),
        ),
        _display_row(
            "Логистика",
            _format_display_money(finance.get("logistics")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("logistics"), warning=row_warning),
        ),
        _display_row(
            "Хранение",
            _format_display_money(finance.get("storage")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("storage"), warning=row_warning),
        ),
        _display_row(
            "Эквайринг",
            _format_display_money(finance.get("acquiring")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("acquiring"), warning=row_warning),
        ),
    ]
    return {
        "title": "Финансы",
        "subtitle": "Финальный финансовый контур за операционный день.",
        "rows": rows,
        "status": section_status,
    }


def build_live_section_v2(live_operational: dict[str, Any]) -> SectionV2:
    live = _safe_dict(live_operational)
    orders = _safe_dict(live.get("orders"))
    sales = _safe_dict(live.get("sales"))
    stocks = _safe_dict(live.get("stocks"))
    section_status = _safe_str(live.get("status")) or "unavailable"

    rows: list[DisplayRowV2] = [
        _display_row(
            "Оперативные заказы",
            _format_display_int(orders.get("count"), "шт"),
            note=f"{_format_display_money(orders.get('amount'))}; источник: {_format_display_text(orders.get('source'))}",
            status=_display_status(bool(orders.get("available", False)), orders.get("count")),
        ),
        _display_row(
            "Оперативные продажи",
            _format_display_int(sales.get("count"), "шт"),
            note=f"{_format_display_money(sales.get('amount'))}; источник: {_format_display_text(sales.get('source'))}",
            status=_display_status(bool(sales.get("available", False)), sales.get("count")),
        ),
        _display_row(
            "Остатки",
            _format_display_int(stocks.get("total_units"), "шт"),
            note=f"Источник: {_format_display_text(stocks.get('source'))}",
            status=_display_status(bool(stocks.get("available", False)), stocks.get("total_units")),
        ),
        _display_row(
            "Дата среза остатков",
            _format_display_text(stocks.get("snapshot_date")),
            note=f"Тип среза: {_format_display_text(stocks.get('snapshot_kind'))}",
            status=_display_status(bool(stocks.get("available", False)), stocks.get("snapshot_date")),
        ),
    ]
    return {
        "title": "Оперативный срез",
        "subtitle": "Оперативные заказы, продажи и остатки без legacy fallback.",
        "rows": rows,
        "status": section_status,
    }


def build_report_payload_v2(
    snapshot: dict[str, Any],
    debug: dict[str, Any] | None = None,
    *,
    artifact_dir: str | Path | None = None,
) -> ReportPayloadV2:
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    if debug is not None and not isinstance(debug, dict):
        raise TypeError("debug must be a dict or None")

    debug_payload = _safe_dict(debug)
    warnings: list[WarningItemV2] = _normalize_debug_warnings(debug_payload.get("warnings"))

    seller_id = _safe_str(snapshot.get("seller_id"))
    report_date = _safe_str(snapshot.get("run_date"))
    operational_date = _safe_str(snapshot.get("operational_date"))
    snapshot_source_mode = _safe_str(snapshot.get("source_mode")) or "unknown"

    cabinet_daily = _safe_dict(snapshot.get("cabinet_commerce_daily"))
    finance_daily = _safe_dict(snapshot.get("finance_final_daily"))
    live_daily = _safe_dict(snapshot.get("live_operational"))

    if not cabinet_daily:
        warnings.append(
            _warning(
                "cabinet_commerce_missing",
                "cabinet_commerce_daily block is missing in snapshot.",
                block="cabinet_commerce",
            )
        )
    elif not bool(cabinet_daily.get("available", False)):
        warnings.append(
            _warning(
                "cabinet_commerce_unavailable",
                "cabinet_commerce_daily is present but marked unavailable.",
                block="cabinet_commerce",
            )
        )

    if not finance_daily:
        warnings.append(
            _warning(
                "finance_final_missing",
                "finance_final_daily block is missing in snapshot.",
                block="finance_final",
            )
        )
    elif not bool(finance_daily.get("available", False)):
        warnings.append(
            _warning(
                "finance_final_unavailable",
                "finance_final_daily is present but marked unavailable.",
                block="finance_final",
            )
        )
    elif finance_daily.get("date_aligned") is False:
        warnings.append(
            _warning(
                "finance_final_lagged",
                "finance_final_daily actual_date differs from operational_date.",
                block="finance_final",
            )
        )

    live_orders = _safe_dict(live_daily.get("orders"))
    live_sales = _safe_dict(live_daily.get("sales"))
    live_stocks = _safe_dict(live_daily.get("stocks"))
    if not live_daily:
        warnings.append(
            _warning(
                "live_operational_missing",
                "live_operational block is missing in snapshot.",
                block="live_operational",
            )
        )
    else:
        if not live_orders:
            warnings.append(_warning("live_orders_missing", "live_operational.orders is missing.", block="live_operational"))
        if not live_sales:
            warnings.append(_warning("live_sales_missing", "live_operational.sales is missing.", block="live_operational"))
        if not live_stocks:
            warnings.append(_warning("live_stocks_missing", "live_operational.stocks is missing.", block="live_operational"))

    buyouts_count, buyouts_amount, buyouts_owner, buyouts_source = _resolve_buyouts_owner(
        cabinet_daily=cabinet_daily,
        finance_daily=finance_daily,
        warnings=warnings,
    )

    live_availability_flags = [
        bool(live_orders.get("available", False)),
        bool(live_sales.get("available", False)),
        bool(live_stocks.get("available", False)),
    ]
    if all(live_availability_flags) and live_availability_flags:
        live_status = "ok"
    elif any(live_availability_flags):
        live_status = "partial"
    else:
        live_status = "unavailable"
    live_block = {
        "status": live_status,
        "orders": _build_live_metric(live_orders),
        "sales": _build_live_metric(live_sales),
        "stocks": _build_live_metric(live_stocks),
    }

    meta_block = {
        "contract_version": "report_payload_v2",
        "seller_id": seller_id,
        "report_date": report_date,
        "operational_date": operational_date,
        "snapshot_source_mode": snapshot_source_mode,
        "debug_available": debug is not None,
    }
    cabinet_block = _build_commerce_block_with_live_fallback(
        cabinet_daily=cabinet_daily,
        live_block=live_block,
        buyouts_count=buyouts_count,
        buyouts_amount=buyouts_amount,
        buyouts_owner=buyouts_owner,
        buyouts_source=buyouts_source,
        warnings=warnings,
    )
    finance_block = {
        "available": bool(finance_daily.get("available", False)) and bool(finance_daily),
        "source": _safe_str(finance_daily.get("source")) or "missing",
        "owner_block": "finance_final_daily",
        "status": (
            "unavailable"
            if not bool(finance_daily.get("available", False))
            else ("lagged" if finance_daily.get("date_aligned") is False else "ok")
        ),
        "target_date": _safe_str(finance_daily.get("target_date")) or None,
        "actual_date": _safe_str(finance_daily.get("actual_date")) or None,
        "date_aligned": finance_daily.get("date_aligned") if "date_aligned" in finance_daily else None,
        "gross_revenue": _safe_float(finance_daily.get("gross_revenue")),
        "seller_payout": _safe_float(finance_daily.get("seller_payout")),
        "wb_commission": _safe_float(finance_daily.get("wb_commission")),
        "logistics": _safe_float(finance_daily.get("logistics")),
        "storage": _safe_float(finance_daily.get("storage")),
        "acquiring": _safe_float(finance_daily.get("acquiring")),
        "penalties": _safe_float(finance_daily.get("penalties")),
        "deductions": _safe_float(finance_daily.get("deductions")),
        "tax": _safe_float(finance_daily.get("tax")),
    }
    ads_efficiency_section = build_ads_efficiency_section_v2(snapshot, debug, artifact_dir=artifact_dir)
    for item in ads_efficiency_section.get("warnings", []):
        if isinstance(item, dict):
            _append_once(warnings, item)
    query_profitability_section = build_query_profitability_section_v2(
        snapshot,
        debug,
        artifact_dir=artifact_dir,
    )
    sku_health_section = build_sku_health_section_v2(snapshot, debug, artifact_dir=artifact_dir)
    for item in sku_health_section.get("warnings", []):
        if isinstance(item, dict):
            _append_once(warnings, item)
    profit_contribution_section = build_profit_contribution_section_v2(
        snapshot,
        debug,
        artifact_dir=artifact_dir,
        sku_health_section=sku_health_section,
    )
    for item in profit_contribution_section.get("warnings", []):
        if isinstance(item, dict):
            _append_once(warnings, item)
    abc_analysis_section = build_abc_analysis_section_v2(snapshot, debug, artifact_dir=artifact_dir)
    for item in abc_analysis_section.get("warnings", []):
        if isinstance(item, dict):
            _append_once(warnings, item)
    abc_section = build_abc_section_v2(
        snapshot,
        debug,
        artifact_dir=artifact_dir,
        profit_contribution_section=profit_contribution_section,
    )
    for item in abc_section.get("warnings", []):
        if isinstance(item, dict):
            _append_once(warnings, item)

    payload: ReportPayloadV2 = {
        "meta": meta_block,
        "hero": build_hero_v2(
            meta=meta_block,
            cabinet_commerce=cabinet_block,
            finance_final=finance_block,
            live_operational=live_block,
            warnings=warnings,
        ),
        "cabinet_commerce": cabinet_block,
        "commerce_section": build_commerce_section_v2(cabinet_block),
        "funnel_section": build_funnel_section_v2(snapshot, cabinet_block, debug),
        "ads_efficiency_section": ads_efficiency_section,
        "ads_section": build_ads_section_v2(
            snapshot,
            debug,
            artifact_dir=artifact_dir,
            ads_efficiency_section=ads_efficiency_section,
        ),
        "query_profitability_section": query_profitability_section,
        "sku_health_section": sku_health_section,
        "profit_contribution_section": profit_contribution_section,
        "abc_section": abc_section,
        "abc_analysis_section": abc_analysis_section,
        "finance_final": finance_block,
        "finance_section": build_finance_section_v2(finance_block),
        "finance_alignment_notice": build_finance_alignment_notice_v2(finance_daily),
        "live_operational": live_block,
        "live_section": build_live_section_v2(live_block),
        "warnings": warnings,
        "source_flags": {
            "snapshot_present": True,
            "debug_present": debug is not None,
            "snapshot_source_mode": snapshot_source_mode,
            "buyouts_owner": buyouts_owner,
            "buyouts_source": buyouts_source,
            "warnings_count": len(warnings),
        },
        "diagnostics": build_diagnostics_v2(snapshot, debug, warnings),
    }

    if debug_payload:
        endpoints = debug_payload.get("endpoints")
        payload["debug_summary"] = {
            "endpoints_present": sorted(endpoints.keys()) if isinstance(endpoints, dict) else [],
            "warnings_count": len(_normalize_debug_warnings(debug_payload.get("warnings"))),
        }

    return payload
