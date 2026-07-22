from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
    StockSectionV2,
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


def _safe_decimal(value: Any) -> Decimal | None:
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
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
    numeric = _safe_decimal(value)
    if numeric is None:
        return "нет данных"
    numeric = numeric.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if numeric == numeric.to_integral_value():
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
        _source_flag(
            "live_operational.orders.stale",
            bool(live_orders.get("stale", False)),
            "warning" if bool(live_orders.get("stale", False)) else _availability_status(live_orders),
        ),
        _source_flag("live_operational.sales.available", bool(live_sales.get("available", False)), _availability_status(live_sales)),
        _source_flag(
            "live_operational.sales.stale",
            bool(live_sales.get("stale", False)),
            "warning" if bool(live_sales.get("stale", False)) else _availability_status(live_sales),
        ),
        _source_flag("live_operational.stocks.available", bool(live_stocks.get("available", False)), _availability_status(live_stocks)),
        _source_flag(
            "live_operational.stocks.stale",
            bool(live_stocks.get("stale", False)),
            "warning" if bool(live_stocks.get("stale", False)) else _availability_status(live_stocks),
        ),
        _source_flag("debug_present", debug_present, "ok" if debug_present else "missing"),
    ]

    warnings = _dedupe_diagnostics_warnings(diagnostics_warnings)
    return {
        "warnings": warnings,
        "source_flags": source_flags,
        "warnings_count": len(warnings),
    }


def _resolve_buyouts_owner(
    *, cabinet_daily: dict[str, Any], finance_daily: dict[str, Any], live_sales: dict[str, Any], warnings: list[WarningItemV2]
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

    live_sales_count = _safe_int(live_sales.get("count"))
    live_sales_amount = _safe_float(live_sales.get("amount"))
    if live_sales_count is not None and live_sales_count > 0:
        if cabinet_buyouts_count is not None and cabinet_buyouts_count == 0:
            warnings.append(
                _warning(
                    "buyouts_override_from_sales_api",
                    "Cabinet commerce reported 0 buyouts but sales API confirmed actual sales. Using sales API data.",
                    block="live_operational",
                )
            )
        return (
            live_sales_count,
            live_sales_amount,
            "live_operational_sales",
            _safe_str(live_sales.get("source")) or "sales_api",
        )

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
        "stale": bool(block.get("stale", False)),
        "stale_reason": _safe_str(block.get("stale_reason")) or None,
        "source_actual_date": _safe_str(block.get("source_actual_date")) or None,
        "cache_age_seconds": _safe_float(block.get("cache_age_seconds")),
        "cache_path": _safe_str(block.get("cache_path")) or None,
        "cache_fallback_used": bool(block.get("cache_fallback_used", False)),
    }


def _live_metric_status(block: dict[str, Any], value: Any) -> str:
    status = _display_status(bool(block.get("available", False)), value)
    if status == "ok" and bool(block.get("stale", False)):
        return "warning"
    return status


def _live_stale_note(block: dict[str, Any]) -> str:
    if not bool(block.get("stale", False)):
        return ""
    parts = ["stale/cache fallback"]
    reason = _safe_str(block.get("stale_reason"))
    source_actual_date = _safe_str(block.get("source_actual_date"))
    cache_age_seconds = _safe_float(block.get("cache_age_seconds"))
    if reason:
        parts.append(f"reason={reason}")
    if source_actual_date:
        parts.append(f"source_actual_date={source_actual_date}")
    if cache_age_seconds is not None:
        parts.append(f"cache_age_seconds={round(cache_age_seconds, 2)}")
    return "; ".join(parts)


def _join_notes(*parts: str) -> str:
    return "; ".join(part for part in (_safe_str(item) for item in parts) if part)


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
    realized_sales_qty = _first_numeric(finance, ("realized_sales_qty",))
    realized_sales_revenue = _first_numeric(finance, ("sale_customer_revenue",))
    realized_status = "unavailable"
    if finance_available and (realized_sales_qty is not None or realized_sales_revenue is not None):
        realized_status = "warning" if finance_status == "lagged" else "ok"
    payout_status = "unavailable"
    if finance_available and finance.get("seller_payout") is not None:
        payout_status = "warning" if finance_status == "lagged" else "ok"
    returns_qty = _first_numeric(finance, ("returns_qty",))
    deliveries_qty = _first_numeric(finance, ("deliveries_qty", "delivery_count"))
    returns_status = "unavailable"
    if finance_available and returns_qty is not None:
        returns_status = "warning" if finance_status == "lagged" else "ok"
    stocks_status = "ok" if stocks_available and stocks.get("total_units") is not None else "unavailable"
    orders_subvalue = _format_hero_money(cabinet.get("orders_amount"))
    if bool(cabinet.get("orders_fallback", False)):
        orders_subvalue = (
            f"{orders_subvalue}; {_safe_str(cabinet.get('orders_source')) or 'orders_api'}; оперативно"
        )
    returns_subvalue = _safe_str(finance.get("source")) or "finance_final_daily"
    if deliveries_qty is not None:
        returns_subvalue = f"Доставки: {_format_hero_int(deliveries_qty, 'шт')}"

    cards: list[HeroKpiCardV2] = [
        {
            "label": "Заказы",
            "value": _format_hero_int(cabinet.get("orders_count"), "шт"),
            "subvalue": orders_subvalue,
            "status": orders_status,
        },
    ]
    if stocks_status != "unavailable":
        cards.append(
            {
                "label": "Остатки",
                "value": _format_hero_int(stocks.get("total_units"), "шт"),
                "subvalue": "",
                "status": stocks_status,
            }
        )
    if realized_sales_qty is not None:
        cards.append(
            {
                "label": "Продажи",
                "value": _format_hero_int(realized_sales_qty, "шт"),
                "subvalue": _format_hero_money(realized_sales_revenue),
                "status": realized_status,
            }
        )
    if finance.get("seller_payout") is not None:
        cards.append(
            {
                "label": "К перечислению",
                "value": _format_hero_money(finance.get("seller_payout")),
                "subvalue": "",
                "status": payout_status,
            }
        )
    if returns_qty is not None:
        cards.append(
            {
                "label": "Возвраты",
                "value": _format_hero_int(returns_qty, "шт"),
                "subvalue": "",
                "status": returns_status,
            }
        )

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
    return {
        "title": "Заказы и выкупы",
        "subtitle": "",
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


def _load_previous_funnel_from_history(
    snapshot: dict[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load previous day's funnel data from history index."""
    seller_id = _safe_str(snapshot.get("seller_id"))
    operational_date = _safe_str(snapshot.get("operational_date") or snapshot.get("run_date"))
    if not seller_id or not operational_date:
        return {}

    from datetime import datetime, timedelta

    try:
        today = datetime.strptime(operational_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {}

    yesterday = (today - timedelta(days=1)).isoformat()
    week_ago = (today - timedelta(days=7)).isoformat()

    root = Path(repo_root) if repo_root is not None else Path(".")
    history_index_path = root / "cabinets" / seller_id / "history" / "history_index.json"
    if not history_index_path.is_file() and repo_root is None:
        alt = Path("..") / "cabinets" / seller_id / "history" / "history_index.json"
        if alt.is_file():
            history_index_path = alt
        else:
            return {}

    index = _read_json_dict(history_index_path)
    snapshots_list = index.get("snapshots", []) if isinstance(index, dict) else []
    if not isinstance(snapshots_list, list) or not snapshots_list:
        return {}

    date_kpi: dict[str, dict[str, Any]] = {}
    for snap_meta in snapshots_list:
        if isinstance(snap_meta, dict):
            d = _safe_str(snap_meta.get("date"))
            kpi = snap_meta.get("kpi") or {}
            if d and isinstance(kpi, dict):
                date_kpi[d] = kpi

    return {
        "yesterday": date_kpi.get(yesterday, {}).get("funnel", {}),
        "week_ago": date_kpi.get(week_ago, {}).get("funnel", {}),
    }


def _funnel_delta_pct(current: Any, previous: Any) -> str:
    c = _safe_float(current)
    p = _safe_float(previous)
    if c is None or p is None:
        return "н/д"
    if p == 0:
        return "н/д"
    pct = round((c - p) / abs(p) * 100, 1)
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct}%"


def _history_funnel_numeric(block: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(block.get(key))
        if value is not None:
            return value
    return None


def _funnel_history_comparison(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, dict[str, str]]:
    aliases = {
        "open_count": ("open_count", "clicks"),
        "cart_count": ("cart_count", "cart"),
        "orders_count": ("orders_count", "orders"),
        "buyouts_count": ("buyouts_count", "buyouts"),
    }

    def value(block: dict[str, Any], key: str) -> float | None:
        return _history_funnel_numeric(block, *aliases[key])

    def rate(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator * 100

    def count_text(number: float | None) -> str:
        if number is None:
            return "н/д"
        return f"{int(number)} шт" if number == int(number) else f"{number} шт"

    comparison: dict[str, dict[str, str]] = {}
    for label, key in (
        ("Переходы в карточку", "open_count"),
        ("Корзина", "cart_count"),
        ("Заказы", "orders_count"),
        ("Выкупы", "buyouts_count"),
    ):
        current_value = value(current, key)
        previous_value = value(previous, key)
        comparison[label] = {
            "today": count_text(current_value),
            "yesterday": count_text(previous_value),
            "vs_yesterday": _funnel_delta_pct(current_value, previous_value),
        }

    for label, numerator_key, denominator_key in (
        ("Карточка → Корзина", "cart_count", "open_count"),
        ("Корзина → Заказ", "orders_count", "cart_count"),
        ("Заказ → Выкуп", "buyouts_count", "orders_count"),
    ):
        current_numerator = value(current, numerator_key)
        current_denominator = value(current, denominator_key)
        previous_numerator = value(previous, numerator_key)
        previous_denominator = value(previous, denominator_key)
        current_rate = rate(current_numerator, current_denominator)
        previous_rate = rate(previous_numerator, previous_denominator)
        comparison[label] = {
            "today": f"{current_rate:.1f}%" if current_rate is not None else "нет данных",
            "yesterday": f"{previous_rate:.1f}%" if previous_rate is not None else "нет данных",
            "vs_yesterday": _funnel_delta_pct(current_rate, previous_rate),
        }
    return comparison


def build_funnel_section_v2(
    snapshot: dict[str, Any],
    cabinet_commerce: dict[str, Any],
    debug: dict[str, Any] | None,
    *,
    repo_root: str | Path | None = None,
) -> FunnelSectionV2:
    _ = debug
    safe_snapshot = _safe_dict(snapshot)
    funnel_daily = _safe_dict(safe_snapshot.get("funnel_daily"))
    if funnel_daily and bool(funnel_daily.get("available", False)):
        source = _safe_str(funnel_daily.get("source")) or "sales_funnel_api"
        status = _safe_str(funnel_daily.get("status")).lower() or "ok"
        if status not in {"ok", "partial"}:
            status = "partial"

        live_operational = _safe_dict(safe_snapshot.get("live_operational"))
        live_sales = _safe_dict(live_operational.get("sales"))
        live_sales_count = _safe_int(live_sales.get("count"))
        live_sales_amount = _safe_float(live_sales.get("amount"))
        funnel_buyouts = _safe_int(funnel_daily.get("buyouts_count"))
        if (not funnel_buyouts or funnel_buyouts == 0) and live_sales_count and live_sales_count > 0:
            funnel_daily = dict(funnel_daily)
            funnel_daily["buyouts_count"] = live_sales_count
            funnel_daily["buyouts_amount"] = live_sales_amount
            funnel_daily["order_to_buyout_rate"] = round(live_sales_count / funnel_daily.get("orders_count", 1) * 100, 2) if funnel_daily.get("orders_count") else 0

        live_operational = _safe_dict(safe_snapshot.get("live_operational"))
        live_sales = _safe_dict(live_operational.get("sales"))
        live_sales_count = _safe_int(live_sales.get("count"))
        live_sales_amount = _safe_float(live_sales.get("amount"))
        funnel_buyouts = _safe_int(funnel_daily.get("buyouts_count"))
        if (not funnel_buyouts or funnel_buyouts == 0) and live_sales_count and live_sales_count > 0:
            funnel_daily = dict(funnel_daily)
            funnel_daily["buyouts_count"] = live_sales_count
            funnel_daily["buyouts_amount"] = live_sales_amount
            funnel_daily["order_to_buyout_rate"] = round(live_sales_count / funnel_daily.get("orders_count", 1) * 100, 2) if funnel_daily.get("orders_count") else 0

        card_opens = _safe_int(funnel_daily.get("open_count") or funnel_daily.get("card_opens"))
        cart = _safe_int(funnel_daily.get("cart_count"))
        orders = _safe_int(funnel_daily.get("orders_count"))
        buyouts = _safe_int(funnel_daily.get("buyouts_count"))

        rows: list[FunnelStageRowV2] = [
            _funnel_daily_count_row("Переходы в карточку", funnel_daily, "open_count", source=source),
            _funnel_daily_count_row("Корзина", funnel_daily, "cart_count", source=source),
            _funnel_daily_count_row("Заказы", funnel_daily, "orders_count", source=source),
            _funnel_daily_count_row("Выкупы", funnel_daily, "buyouts_count", source=source),
            _funnel_daily_rate_row("Карточка → Корзина", funnel_daily, "open_to_cart_rate", source=source),
            _funnel_daily_rate_row("Корзина → Заказ", funnel_daily, "cart_to_order_rate", source=source),
            _funnel_daily_rate_row("Заказ → Выкуп", funnel_daily, "order_to_buyout_rate", source=source),
        ]

        prev_funnel = _load_previous_funnel_from_history(safe_snapshot, repo_root=repo_root)
        prev_y = _safe_dict(prev_funnel.get("yesterday"))
        prev_w = _safe_dict(prev_funnel.get("week_ago"))
        if prev_y or prev_w:
            delta_metrics = [
                ("Переходы в карточку", card_opens, "open_count"),
                ("Корзина", cart, "cart_count"),
                ("Заказы", orders, "orders_count"),
                ("Выкупы", buyouts, "buyouts_count"),
            ]
            for label, current_val, key in delta_metrics:
                y_val = _safe_float(prev_y.get(key))
                w_val = _safe_float(prev_w.get(key))
                if y_val is not None or w_val is not None:
                    y_text = _funnel_delta_pct(current_val, y_val) if y_val is not None else "н/д"
                    w_text = _funnel_delta_pct(current_val, w_val) if w_val is not None else "н/д"
                    rows.append(
                        _funnel_row(
                            f"{label} (Δ вчера / 7 дн.)",
                            f"{y_text} / {w_text}",
                            source="history",
                            status="ok",
                        )
                    )

        return {
            "title": "Воронка продаж",
            "subtitle": "",
            "rows": rows,
            "history_comparison": _funnel_history_comparison(funnel_daily, prev_y),
            "status": status,
            "message": "",
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
        _upper_funnel_stage_row("Переходы в карточку", upper, ("open_count", "card_opens", "views")),
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

    prev_funnel = _load_previous_funnel_from_history(safe_snapshot, repo_root=repo_root)
    prev_y = _safe_dict(prev_funnel.get("yesterday"))
    prev_w = _safe_dict(prev_funnel.get("week_ago"))
    if prev_y or prev_w:
        delta_items = [
            ("Заказы", orders_count, "orders"),
            ("Выкупы", buyouts_count or sales_count, "buyouts"),
        ]
        for label, current_val, key in delta_items:
            y_val = _safe_float(prev_y.get(key))
            w_val = _safe_float(prev_w.get(key))
            if y_val is not None or w_val is not None:
                y_text = _funnel_delta_pct(current_val, y_val) if y_val is not None else "н/д"
                w_text = _funnel_delta_pct(current_val, w_val) if w_val is not None else "н/д"
                rows.append(
                    _funnel_row(
                        f"{label} (Δ вчера / 7 дн.)",
                        f"{y_text} / {w_text}",
                        source="history",
                        status="ok",
                    )
                )

    return {
        "title": "Воронка продаж",
        "subtitle": "События карточки и заказа; финансовая реализация считается отдельно.",
        "rows": rows,
        "history_comparison": _funnel_history_comparison(
            {
                "open_count": _history_funnel_numeric(upper, "open_count", "card_opens", "views"),
                "cart_count": _history_funnel_numeric(upper, "cart_count", "add_to_cart", "basket_count"),
                "orders_count": orders_count,
                "buyouts_count": buyouts_count if buyouts_count is not None else sales_count,
            },
            prev_y,
        ),
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


def _finance_logistics_amount(block: dict[str, Any]) -> float | None:
    explicit_amount = _safe_float(block.get("logistics_amount"))
    if explicit_amount is not None:
        return explicit_amount
    legacy_amount = _safe_float(block.get("logistics"))
    deliveries_qty = _first_numeric(block, ("deliveries_qty", "delivery_count"))
    if legacy_amount is not None and deliveries_qty is not None and abs(legacy_amount - deliveries_qty) < 1e-9:
        return None
    return legacy_amount


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


def _repo_root_from_artifact_dir(artifact_dir: str | Path | None) -> Path:
    if artifact_dir is None:
        return Path(".")
    start = Path(artifact_dir)
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if candidate.name.lower() == "cabinets":
            return candidate.parent
    return start


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
        ("ДРР рекламы", section.get("drr"), "percent", "расход / выручка из рекламы"),
        ("ДРР по кабинету", section.get("drr_cabinet"), "percent", "расход / сумма выкупов"),
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

    live = _safe_dict(safe_snapshot.get("live_operational"))
    live_ads = _safe_dict(live.get("ads"))
    live_ads_rows = live_ads.get("rows", []) if isinstance(live_ads.get("rows"), list) else []
    live_ads_spend_total = live_ads.get("ads_spend_total") or 0

    if advertising_efficiency and str(advertising_efficiency.get("status", "")).lower() in ("disabled", "no_data"):
        if live_ads_rows:
            advertising_efficiency = {}

    if not advertising_efficiency and live_ads_rows:
        total_spend = live_ads_spend_total or sum(
            abs(_safe_float(r.get("ads_spend")) or _safe_float(r.get("spend")) or 0) for r in live_ads_rows
        )
        total_impressions = sum(int(_safe_float(r.get("impressions")) or 0) for r in live_ads_rows)
        total_clicks = sum(int(_safe_float(r.get("clicks")) or 0) for r in live_ads_rows)
        total_cart = sum(int(_safe_float(r.get("add_to_cart")) or 0) for r in live_ads_rows)
        total_orders_ads = sum(int(_safe_float(r.get("orders")) or 0) for r in live_ads_rows)
        ctr = round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else None
        cpc = round(total_spend / total_clicks, 2) if total_clicks > 0 else None
        cpm = round(total_spend / total_impressions * 1000, 2) if total_impressions > 0 else None
        advertising_efficiency = {
            "source": "live_operational.ads",
            "status": "ok",
            "spend": total_spend,
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr": ctr,
            "cpc": cpc,
            "cpm": cpm,
            "ad_orders": total_orders_ads,
            "portfolio_ad_spend": total_spend,
            "total_ad_spend": total_spend,
        }
    summary = _first_dict(
        advertising_efficiency.get("portfolio_ads_summary"),
        advertising_efficiency.get("advertising_efficiency_summary"),
        advertising_efficiency.get("summary"),
        safe_snapshot.get("portfolio_ads_summary"),
        safe_snapshot.get("advertising_efficiency_summary"),
        artifacts.get("portfolio_ads_summary"),
        artifacts.get("advertising_efficiency_summary"),
    )
    if summary and str(summary.get("analysis_mode", "")).lower() in ("disabled",):
        if live_ads_rows:
            summary = {}
    query_profitability = _first_dict(
        advertising_efficiency.get("query_profitability"),
        safe_snapshot.get("query_profitability"),
        artifacts.get("query_profitability"),
    )
    if query_profitability and str(query_profitability.get("status", "")).lower() in ("disabled", "no_data"):
        if live_ads_rows:
            query_profitability = {}
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
    drr_ads = _pick_numeric((summary, ("portfolio_DRR", "DRR", "drr")), (advertising_efficiency, ("DRR", "drr")))
    if drr_ads is None:
        drr_rate = _safe_divide(spend, ad_revenue)
        drr_ads = round(drr_rate * 100.0, 4) if drr_rate is not None else None

    live_sales_amount = _safe_float(_safe_dict(_safe_dict(safe_snapshot.get("live_operational")).get("sales")).get("amount")) or 0
    cabinet_buyouts_amount = _safe_float(_safe_dict(safe_snapshot.get("cabinet_commerce_daily")).get("buyouts_amount")) or live_sales_amount
    drr_cabinet = round(spend / cabinet_buyouts_amount * 100, 2) if cabinet_buyouts_amount > 0 and (spend or 0) > 0 else None
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

    search_insights_data = None
    if artifact_dir:
        for directory in _artifact_dirs(artifact_dir):
            insights_path = directory / "search_insights.json"
            if insights_path.is_file():
                try:
                    search_insights_data = json.loads(insights_path.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    pass
                if search_insights_data:
                    break

    if search_insights_data and isinstance(search_insights_data, dict):
        unprofitable_queries = search_insights_data.get("unprofitable", [])
        effective_queries = search_insights_data.get("effective", [])
        search_unprofitable_spend = sum(_safe_float(r.get("spend")) or 0 for r in unprofitable_queries)
        search_effective_orders = sum(_safe_int(r.get("orders")) or 0 for r in effective_queries)
        price_map = {898642228: 2800, 969315704: 2800, 333615320: 1480, 452102417: 780, 453526507: 840, 590614192: 720, 283212418: 450}
        search_effective_revenue = sum((_safe_int(r.get("orders")) or 0) * price_map.get(_safe_int(r.get("nmId")) or 0, 0) for r in effective_queries)
        search_effective_spend = sum(_safe_float(r.get("spend")) or 0 for r in effective_queries)

        if not wasted_spend or wasted_spend == 0:
            wasted_spend = search_unprofitable_spend
        if inefficient_items_count is None or inefficient_items_count == 0:
            inefficient_items_count = len(unprofitable_queries)
        if not ad_orders or ad_orders == 0:
            ad_orders = search_effective_orders
        if not ad_revenue or ad_revenue == 0:
            ad_revenue = search_effective_revenue
        if spend and spend > 0 and ad_revenue and ad_revenue > 0:
            drr_ads = round(spend / ad_revenue * 100, 2)
            profit_from_ads = ad_revenue - spend
            roas = round(ad_revenue / spend, 2) if spend > 0 else None

    warnings = _normalize_ads_warnings(advertising_efficiency.get("warnings"))
    values_for_status = [spend, ad_orders, ad_revenue, drr_ads, romi, cpo, impressions, clicks]
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
        "drr": drr_ads,
        "drr_cabinet": drr_cabinet,
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
            "title": "Товары категории А",
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
        "title": "Товары категории А",
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
    abc_basis = _first_text(*[row.get("basis") for row in _abc_raw_rows(payload)])
    abc_basis_label = {
        "buys": "по количеству выкупов",
        "buyouts": "по количеству выкупов",
        "revenue": "по выручке",
        "profit": "по прибыли",
    }.get(abc_basis.lower(), abc_basis)

    has_valid_data = False
    if isinstance(payload, list):
        positive_profits = sum(1 for r in payload if isinstance(r, dict) and (_safe_float(r.get("profit")) or 0) > 0)
        has_valid_data = positive_profits >= 2
    elif isinstance(payload, dict):
        items = payload.get("items") or payload.get("rows") or []
        positive_profits = sum(1 for r in items if isinstance(r, dict) and (_safe_float(r.get("profit")) or 0) > 0)
        has_valid_data = positive_profits >= 2

    if not has_valid_data:
        live = _safe_dict(snapshot.get("live_operational"))
        sales_block = _safe_dict(live.get("sales"))
        orders_block = _safe_dict(live.get("orders"))
        finance = _safe_dict(snapshot.get("finance_final_daily"))
        sales_rows = sales_block.get("rows", []) if isinstance(sales_block.get("rows"), list) else []
        orders_rows = orders_block.get("rows", []) if isinstance(orders_block.get("rows"), list) else []
        finance_rows = finance.get("rows", []) if isinstance(finance.get("rows"), list) else []

        cogs_map_local = {
            nm_id: float(amount)
            for nm_id, amount in _load_cogs_by_nm_id(artifact_dir).items()
        }
        sku_rev_profit: dict[str, dict[str, float]] = {}

        finance_by_sku: dict[str, dict[str, float]] = {}
        for row in finance_rows:
            nm_id = row.get("nm_id")
            if not nm_id:
                continue
            key = str(nm_id)
            rev = abs(_safe_float(row.get("realized_sales_revenue")) or _safe_float(row.get("wb_realized_revenue")) or 0)
            comm = abs(_safe_float(row.get("wb_commission")) or 0)
            logist = abs(_safe_float(row.get("logistics_amount")) or 0)
            stor = abs(_safe_float(row.get("storage")) or 0)
            acqu = abs(_safe_float(row.get("acquiring")) or 0)
            ded = abs(_safe_float(row.get("deductions")) or 0)
            if key not in finance_by_sku:
                finance_by_sku[key] = {"revenue": 0.0, "commission": 0.0, "logistics": 0.0, "storage": 0.0, "acquiring": 0.0, "deductions": 0.0}
            finance_by_sku[key]["revenue"] += rev
            finance_by_sku[key]["commission"] += comm
            finance_by_sku[key]["logistics"] += logist
            finance_by_sku[key]["storage"] += stor
            finance_by_sku[key]["acquiring"] += acqu
            finance_by_sku[key]["deductions"] += ded

        for row in sales_rows:
            nm_id = row.get("nm_id") or row.get("nmId")
            if not nm_id:
                continue
            key = str(nm_id)
            qty = _safe_float(row.get("quantity")) or 1
            amount = _safe_float(row.get("amount")) or 0
            try:
                nm_int = int(nm_id)
            except (TypeError, ValueError):
                nm_int = None
            cogs_val = cogs_map_local.get(nm_int, 0) * int(qty) if nm_int else 0

            fin = finance_by_sku.get(key)
            if amount > 0:
                rev = amount
                if fin and fin["revenue"] > 0:
                    scale = rev / fin["revenue"] if fin["revenue"] > 0 else 1.0
                    total_exp = (fin["commission"] + fin["logistics"] + fin["storage"] + fin["acquiring"] + fin["deductions"]) * scale + cogs_val
                else:
                    total_exp = cogs_val
                profit = rev - total_exp
            elif fin and fin["revenue"] > 0:
                rev = fin["revenue"]
                total_exp = fin["commission"] + fin["logistics"] + fin["storage"] + fin["acquiring"] + fin["deductions"] + cogs_val
                profit = rev - total_exp
            else:
                rev = 0
                profit = 0

            if key in sku_rev_profit:
                sku_rev_profit[key]["revenue"] += rev
                sku_rev_profit[key]["profit"] += profit
            else:
                sku_rev_profit[key] = {"revenue": rev, "profit": profit}

        for key, fin in finance_by_sku.items():
            if key not in sku_rev_profit and fin["revenue"] > 0:
                total_exp = fin["commission"] + fin["logistics"] + fin["storage"] + fin["acquiring"] + fin["deductions"]
                sku_rev_profit[key] = {"revenue": fin["revenue"], "profit": fin["revenue"] - total_exp}

        if not sku_rev_profit:
            detail = _build_sku_detail_section(snapshot, artifact_dir=artifact_dir)
            for s in detail.get("top_skus", []) + detail.get("loss_skus", []):
                nm = str(s.get("nm_id", ""))
                if nm:
                    sku_rev_profit[nm] = {"revenue": s.get("revenue", 0), "profit": s.get("profit", 0)}

        if sku_rev_profit:
            total_deductions_val = abs(_safe_float(finance.get("deductions")) or 0)
            total_rev_for_ded = sum(v["revenue"] for v in sku_rev_profit.values() if v["revenue"] > 0)
            for k, v in sku_rev_profit.items():
                if v["revenue"] > 0 and total_rev_for_ded > 0:
                    ded_share = total_deductions_val * (v["revenue"] / total_rev_for_ded)
                    v["profit"] -= ded_share

            sales_only_skus = {str(row.get("nm_id") or row.get("nmId")) for row in sales_rows if row.get("nm_id") or row.get("nmId")}
            rows_for_abc = [{"sku": k, "revenue": v["revenue"], "profit": v["profit"]} for k, v in sku_rev_profit.items() if k in sales_only_skus and v["revenue"] > 0]
            if not rows_for_abc:
                rows_for_abc = [{"sku": k, "revenue": v["revenue"], "profit": v["profit"]} for k, v in sku_rev_profit.items() if v["revenue"] > 0]
            ad_spend_index = {}
            for _ar in (snapshot.get("live_ads_rows") or []) if isinstance(snapshot, dict) else []:
                if isinstance(_ar, dict):
                    _nm = str(_ar.get("nm_id") or _ar.get("sku") or "")
                    _sp = abs(_safe_float(_ar.get("ads_spend") or _ar.get("spend") or 0))
                    if _nm and _sp > 0:
                        ad_spend_index[_nm] = _sp
            if not ad_spend_index and artifact_dir:
                try:
                    import json as _aj
                    _rr_path = Path(artifact_dir) / "reconciled_rows.json"
                    if _rr_path.is_file():
                        _rr = _aj.load(open(_rr_path, encoding="utf-8"))
                        for _ar in (_rr.get("live_ads_rows") or []):
                            if isinstance(_ar, dict):
                                _nm = str(_ar.get("nm_id") or _ar.get("sku") or "")
                                _sp = abs(_safe_float(_ar.get("ads_spend") or _ar.get("spend") or 0))
                                if _nm and _sp > 0:
                                    ad_spend_index[_nm] = _sp
                except Exception:
                    pass
                if isinstance(_ar, dict):
                    _nm = str(_ar.get("nm_id") or _ar.get("sku") or "")
                    _sp = abs(_safe_float(_ar.get("ads_spend") or _ar.get("spend") or 0))
                    if _nm and _sp > 0 and _nm not in ad_spend_index:
                        ad_spend_index[_nm] = _sp
            existing_skus = {r["sku"] for r in rows_for_abc}
            for _nm, _sp in ad_spend_index.items():
                if _nm not in existing_skus:
                    rows_for_abc.append({"sku": _nm, "revenue": 0, "profit": -_sp})
            rows_for_abc.sort(key=lambda r: r["profit"], reverse=True)
            positive_profit_total = sum(r["profit"] for r in rows_for_abc if r["profit"] > 0)
            total_revenue = sum(r["revenue"] for r in rows_for_abc)
            cumulative = 0.0
            computed = []
            for r in rows_for_abc:
                rev_share = r["revenue"] / total_revenue if total_revenue > 0 else 0
                if r["profit"] <= 0 or positive_profit_total <= 0:
                    abc_class = "C"
                else:
                    cumulative += r["profit"] / positive_profit_total
                    if cumulative <= 0.80:
                        abc_class = "A"
                    elif cumulative <= 0.95:
                        abc_class = "B"
                    else:
                        abc_class = "C"
                computed.append({
                    "sku": r["sku"],
                    "revenue": round(r["revenue"], 2),
                    "profit": round(r["profit"], 2),
                    "share": round(rev_share, 6),
                    "cumulative_share": round(cumulative, 6),
                    "abc_class": abc_class,
                })
            payload = computed

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
        "subtitle": (
            f"ABC-категории рассчитаны {abc_basis_label}; C означает низкий вклад, а не отсутствие продаж."
            if abc_basis_label
            else "Вклад SKU, критичные A-SKU и рекламная активность C-SKU."
        ),
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
    logistics_amount = _finance_logistics_amount(finance)

    rows: list[DisplayRowV2] = [
        _display_row(
            "Статус",
            _format_display_text(finance_status),
            note=f"Операционный день: {target_date}; финансы: {actual_date}; реализация и операции WB",
            status=section_status,
        ),
        _display_row(
            "Продажи/реализация",
            _format_display_int(finance.get("realized_sales_qty"), "шт"),
            note=f"{_format_display_money(finance.get('realized_sales_revenue'))}; источник: {source}",
            status=_display_status(
                available,
                finance.get("realized_sales_qty")
                if finance.get("realized_sales_qty") is not None
                else finance.get("realized_sales_revenue"),
                warning=row_warning,
            ),
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
            "Возвраты",
            _format_display_int(finance.get("returns_qty"), "шт"),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("returns_qty"), warning=row_warning),
        ),
        _display_row(
            "Доставки",
            _format_display_int(finance.get("deliveries_qty"), "шт"),
            note="Количество доставок не используется как денежная логистика.",
            status=_display_status(available, finance.get("deliveries_qty"), warning=row_warning),
        ),
        _display_row(
            "Комиссия WB",
            _format_display_money(finance.get("wb_commission")),
            note=f"Источник: {source}",
            status=_display_status(available, finance.get("wb_commission"), warning=row_warning),
        ),
        _display_row(
            "Логистика",
            _format_display_money(logistics_amount),
            note=f"Денежное поле услуг доставки; источник: {source}",
            status=_display_status(available, logistics_amount, warning=row_warning),
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
        "subtitle": "Финансы считаются по реализации и операциям финансового отчёта WB.",
        "rows": rows,
        "status": section_status,
    }


def build_live_section_v2(live_operational: dict[str, Any]) -> SectionV2:
    live = _safe_dict(live_operational)
    orders = _safe_dict(live.get("orders"))
    sales = _safe_dict(live.get("sales"))
    stocks = _safe_dict(live.get("stocks"))
    section_status = _safe_str(live.get("status")) or "unavailable"
    if any(bool(block.get("stale", False)) for block in (orders, sales, stocks)):
        section_status = "warning"

    rows: list[DisplayRowV2] = [
        _display_row(
            "Оперативные заказы",
            _format_display_int(orders.get("count"), "шт"),
            note=_join_notes(
                f"{_format_display_money(orders.get('amount'))}; источник: {_format_display_text(orders.get('source'))}",
                _live_stale_note(orders),
            ),
            status=_live_metric_status(orders, orders.get("count")),
        ),
        _display_row(
            "Оперативные продажи",
            _format_display_int(sales.get("count"), "шт"),
            note=_join_notes(
                f"{_format_display_money(sales.get('amount'))}; источник: {_format_display_text(sales.get('source'))}",
                _live_stale_note(sales),
            ),
            status=_live_metric_status(sales, sales.get("count")),
        ),
        _display_row(
            "Оперативные остатки",
            _format_display_int(stocks.get("total_units"), "шт"),
            note=_join_notes(
                f"live snapshot stocks_api, дата среза {_format_display_text(stocks.get('snapshot_date'))}; источник: {_format_display_text(stocks.get('source'))}",
                "Оперативные остатки из stocks_api могут отличаться от остатков товарного отчёта WB за операционный день.",
                _live_stale_note(stocks),
            ),
            status=_live_metric_status(stocks, stocks.get("total_units")),
        ),
        _display_row(
            "Дата среза оперативных остатков",
            _format_display_text(stocks.get("snapshot_date")),
            note=_join_notes(
                f"Тип среза: {_format_display_text(stocks.get('snapshot_kind'))}; source: stocks_api live snapshot",
                _live_stale_note(stocks),
            ),
            status=_live_metric_status(stocks, stocks.get("snapshot_date")),
        ),
    ]
    return {
        "title": "Оперативный срез",
        "subtitle": "Оперативные заказы, продажи и live-остатки stocks_api без сравнения с товарным отчётом WB.",
        "rows": rows,
        "status": section_status,
    }


_STOCK_GOODS_EXPLANATION = (
    "Оперативные остатки из stocks_api могут отличаться от остатков товарного отчёта WB за операционный день."
)


def _stock_source_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    for key in ("stock_section", "stock_summary"):
        block = _safe_dict(snapshot.get(key))
        if block:
            return block
    return {}


def build_stock_section_v2(snapshot: dict[str, Any]) -> StockSectionV2:
    stock = _stock_source_block(_safe_dict(snapshot))
    source = _safe_str(stock.get("source")) or "missing"
    stock_wb_qty = _safe_int(_first_numeric(stock, ("stock_wb_qty", "wb_stock_qty", "wb_qty")))
    stock_mp_qty = _safe_int(_first_numeric(stock, ("stock_mp_qty", "mp_stock_qty", "mp_qty")))
    stock_total_qty = _safe_int(_first_numeric(stock, ("stock_total_qty", "total_stock_qty", "stock_qty")))
    if stock_total_qty is None and (stock_wb_qty is not None or stock_mp_qty is not None):
        stock_total_qty = int(stock_wb_qty or 0) + int(stock_mp_qty or 0)
    stock_value = _first_numeric(stock, ("stock_value", "stock_value_rub", "stock_amount"))
    sku_rows_count = _safe_int(_first_numeric(stock, ("sku_rows_count", "sku_count", "rows_count")))
    available = any(
        value is not None
        for value in (stock_wb_qty, stock_mp_qty, stock_total_qty, stock_value, sku_rows_count)
    )

    rows: list[DisplayRowV2] = [
        _display_row(
            "Остатки WB",
            _format_display_int(stock_wb_qty, "шт"),
            note=f"Источник: {_format_display_text(source)}",
            status=_display_status(available, stock_wb_qty),
        ),
        _display_row(
            "Остатки МП",
            _format_display_int(stock_mp_qty, "шт"),
            note=f"Источник: {_format_display_text(source)}",
            status=_display_status(available, stock_mp_qty),
        ),
        _display_row(
            "Всего остатков",
            _format_display_int(stock_total_qty, "шт"),
            note="Не заполняется из live stocks_api без отдельного товарного источника.",
            status=_display_status(available, stock_total_qty),
        ),
        _display_row(
            "Сумма остатков",
            _format_display_money(stock_value),
            note=f"Источник: {_format_display_text(source)}",
            status=_display_status(available, stock_value),
        ),
        _display_row(
            "SKU-строк",
            _format_display_int(sku_rows_count, "шт"),
            note=f"Источник: {_format_display_text(source)}",
            status=_display_status(available, sku_rows_count),
        ),
    ]

    warnings: list[WarningItemV2] = []
    if not available:
        warnings.append(
            _warning(
                "stock_goods_source_missing",
                "Отдельный источник товарных остатков WB/МП не подключён; live stocks_api не используется как полный складской остаток.",
                block="stock_section",
                level="info",
            )
        )

    return {
        "title": "Товарные остатки",
        "subtitle": "Отдельный контур для остатков WB/МП и стоимости запасов; не смешивается с live stocks_api.",
        "available": available,
        "status": "ok" if available else "no_data",
        "source": source if available else "missing",
        "message": (
            "Остатки собраны из отдельного товарного источника."
            if available
            else "Нет отдельного источника stock_wb_qty/stock_mp_qty/stock_value; live stocks_api не подставляется."
        ),
        "stock_wb_qty": stock_wb_qty,
        "stock_mp_qty": stock_mp_qty,
        "stock_total_qty": stock_total_qty,
        "stock_value": stock_value,
        "sku_rows_count": sku_rows_count,
        "rows": rows,
        "warnings": warnings,
    }


_LEGACY_COGS_BY_NM_ID = {
    898642228: Decimal("100"),
    969315704: Decimal("600"),
    333615320: Decimal("210"),
    452102417: Decimal("210"),
    453526507: Decimal("210"),
    590614192: Decimal("180"),
    283212418: Decimal("450"),
}


def _load_cogs_by_nm_id(artifact_dir: str | Path | None) -> dict[int, Decimal]:
    cogs_by_nm_id = dict(_LEGACY_COGS_BY_NM_ID)
    for directory in _artifact_dirs(artifact_dir):
        payload = _read_json_dict(directory / "config" / "cogs.json")
        values = _safe_dict(payload.get("values"))
        if not values:
            continue
        for nm_id, value in values.items():
            nm_id_int = _safe_int(nm_id)
            amount = _safe_decimal(value)
            if nm_id_int is not None and amount is not None:
                cogs_by_nm_id[nm_id_int] = amount
        break
    return cogs_by_nm_id


def _profit_calculation(
    snapshot: dict[str, Any],
    cabinet: dict[str, Any],
    *,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    finance = _safe_dict(snapshot.get("finance_final_daily"))
    revenue = _safe_decimal(cabinet.get("buyouts_amount"))
    if not finance.get("available") or revenue is None:
        return None

    def expense(name: str) -> Decimal:
        return abs(_safe_decimal(finance.get(name)) or Decimal("0"))

    commission = expense("wb_commission")
    logistics_value = _safe_decimal(finance.get("logistics_amount"))
    if logistics_value is None:
        logistics_value = _safe_decimal(finance.get("logistics"))
    rebill_logistic = expense("rebill_logistic_cost")
    storage = expense("storage")
    acquiring = expense("acquiring")
    penalties = expense("penalties")
    deductions = expense("deductions")
    tax = expense("tax")

    finance_rows = finance.get("rows", []) if isinstance(finance.get("rows"), list) else []
    return_groups: dict[tuple[str, str, str], dict[str, Decimal]] = {}
    for raw_row in finance_rows:
        row = _safe_dict(raw_row)
        group_key = (
            _safe_str(row.get("nm_id") or row.get("sku")),
            _safe_str(row.get("order_date")),
            _safe_str(row.get("warehouse")),
        )
        group = return_groups.setdefault(
            group_key,
            {
                "returns_qty": Decimal("0"),
                "reverse_logistics": Decimal("0"),
                "deliveries_qty": Decimal("0"),
                "direct_logistics": Decimal("0"),
            },
        )
        row_returns_qty = _safe_decimal(row.get("returns_qty")) or Decimal("0")
        row_deliveries_qty = _safe_decimal(row.get("deliveries_qty")) or Decimal("0")
        row_logistics = abs(
            _safe_decimal(row.get("logistics_amount"))
            or _safe_decimal(row.get("logistics"))
            or Decimal("0")
        )
        if row_returns_qty > 0:
            group["returns_qty"] += row_returns_qty
            group["reverse_logistics"] += row_logistics
        elif row_deliveries_qty > 0:
            group["deliveries_qty"] += row_deliveries_qty
            group["direct_logistics"] += row_logistics

    return_direct_logistics = Decimal("0")
    return_reverse_logistics = Decimal("0")
    for group in return_groups.values():
        group_returns = group["returns_qty"]
        if group_returns <= 0:
            continue
        return_reverse_logistics += group["reverse_logistics"]
        if group["deliveries_qty"] > 0:
            direct_unit_cost = group["direct_logistics"] / group["deliveries_qty"]
            return_direct_logistics += direct_unit_cost * group_returns
    return_logistics = return_direct_logistics + return_reverse_logistics

    commission_basis = (
        _safe_decimal(finance.get("realized_sales_revenue"))
        or _safe_decimal(finance.get("wb_realized_revenue"))
        or _safe_decimal(finance.get("gross_revenue"))
    )
    commission_rate = None
    if commission_basis is not None and commission_basis > 0:
        commission_rate = (commission / commission_basis * Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    if logistics_value is None:
        seller_payout = _safe_decimal(finance.get("seller_payout")) or Decimal("0")
        logistics_value = max(
            commission
            + revenue
            - seller_payout
            - storage
            - acquiring
            - deductions
            - tax
            - penalties
            - rebill_logistic,
            Decimal("0"),
        )
    logistics = abs(logistics_value)

    live = _safe_dict(snapshot.get("live_operational"))
    sales = _safe_dict(live.get("sales"))
    sales_rows = sales.get("rows", []) if isinstance(sales.get("rows"), list) else []
    cogs_by_nm_id = _load_cogs_by_nm_id(artifact_dir)
    total_cogs = Decimal("0")
    cogs_skus: set[int] = set()
    missing_cogs_skus: set[int] = set()
    for raw_row in sales_rows:
        row = _safe_dict(raw_row)
        nm_id = _safe_int(row.get("nm_id") or row.get("nmId"))
        quantity = _safe_decimal(row.get("quantity"))
        if quantity is None:
            quantity = Decimal("1")
        if nm_id is None or quantity <= 0:
            continue
        unit_cogs = cogs_by_nm_id.get(nm_id)
        if unit_cogs is None:
            missing_cogs_skus.add(nm_id)
            continue
        total_cogs += unit_cogs * quantity
        cogs_skus.add(nm_id)

    ads = _safe_dict(live.get("ads"))
    ads_spend = abs(_safe_decimal(ads.get("ads_spend_total")) or Decimal("0"))
    total_expenses = sum(
        (
            commission,
            logistics,
            rebill_logistic,
            storage,
            acquiring,
            penalties,
            deductions,
            tax,
            total_cogs,
            ads_spend,
        ),
        Decimal("0"),
    )
    net_profit = revenue - total_expenses
    margin = None
    if revenue > 0:
        margin = (net_profit / revenue * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    return {
        "revenue": revenue,
        "commission": commission,
        "logistics": logistics,
        "rebill_logistic": rebill_logistic,
        "storage": storage,
        "acquiring": acquiring,
        "penalties": penalties,
        "deductions": deductions,
        "tax": tax,
        "returns_qty": _safe_decimal(finance.get("returns_qty")) or Decimal("0"),
        "return_direct_logistics": return_direct_logistics,
        "return_reverse_logistics": return_reverse_logistics,
        "return_logistics": return_logistics,
        "commission_basis": commission_basis,
        "commission_rate": commission_rate,
        "total_cogs": total_cogs,
        "ads_spend": ads_spend,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "margin": margin,
        "cogs_skus": sorted(cogs_skus),
        "missing_cogs_skus": sorted(missing_cogs_skus),
    }


def _build_hero_section(
    snapshot: dict[str, Any],
    cabinet_commerce: dict[str, Any] | None = None,
    *,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    cabinet = cabinet_commerce or _safe_dict(snapshot.get("cabinet_commerce_daily"))
    finance = _safe_dict(snapshot.get("finance_final_daily"))
    live = _safe_dict(snapshot.get("live_operational"))
    stocks = _safe_dict(live.get("stocks"))
    ads = _safe_dict(live.get("ads"))

    orders_count = cabinet.get("orders_count") or 0
    orders_amount = cabinet.get("orders_amount") or 0
    buyouts_count = cabinet.get("buyouts_count") or 0
    buyouts_amount = cabinet.get("buyouts_amount") or 0

    calculation = _profit_calculation(snapshot, cabinet, artifact_dir=artifact_dir)
    net_profit = calculation.get("net_profit") if calculation else None
    spend = ads.get("ads_spend_total") or 0
    stock_units = _safe_int(stocks.get("total_units")) if stocks.get("available") else None

    stock_days = None
    sales = _safe_dict(live.get("sales"))
    sales_count = sales.get("count") or 0
    if stock_units is not None and sales_count and sales_count > 0:
        stock_days = round(stock_units / sales_count, 1)

    margin = None
    if calculation:
        margin = calculation.get("margin")

    rows = [
        {"label": "Заказы", "value": f"{int(orders_count)} шт", "status": "ok"},
        {"label": "Сумма заказов", "value": _format_display_money(orders_amount), "status": "ok"},
        {"label": "Выкупы", "value": f"{int(buyouts_count)} шт", "status": "ok"},
        {"label": "Сумма выкупов", "value": _format_display_money(buyouts_amount), "status": "ok"},
    ]
    if net_profit is not None:
        profit_status = "ok"
        if margin is not None:
            if margin > Decimal("15"):
                profit_status = "ok"
            elif margin < Decimal("15"):
                profit_status = "critical"
            else:
                profit_status = "warning"
        rows.append({"label": "Прибыль", "value": _format_display_money(net_profit), "status": profit_status, "note": f"Маржа: {margin}%" if margin else ""})
    rows.append({"label": "Реклама", "value": _format_display_money(-spend) if spend else "0 ₽", "status": "ok"})
    stock_value = "нет данных"
    stock_status = "unavailable"
    if stock_units is not None:
        stock_value = f"{stock_units} шт"
        stock_status = "ok"
        if stock_days is not None:
            stock_value += f" ({int(stock_days)} дн.)"
            if stock_days < 3:
                stock_status = "critical"
            elif stock_days > 60:
                stock_status = "warning"
    rows.append({"label": "Остатки", "value": stock_value, "status": stock_status})

    alerts: list[dict[str, str]] = []
    returns_qty = finance.get("returns_qty") or 0
    if returns_qty and returns_qty > 0:
        alerts.append({"text": f"Возвраты: {int(returns_qty)} шт — проверьте причину", "priority": "warning", "icon": "returns"})
    if margin is not None and margin < Decimal("15"):
        alerts.append({"text": f"Маржа: {margin}% — ниже нормы", "priority": "warning", "icon": "margin"})
    if stock_units is not None and stock_days is not None and stock_days < 3:
        alerts.append({"text": f"Остатки: {int(stock_units)} шт ({int(stock_days)} дн.) — риск дефицита", "priority": "critical", "icon": "stock_low"})

    actions: list[dict[str, str]] = []
    if spend > 0:
        actions.append({"text": "Отключить убыточные запросы", "priority": "warning", "effect": f"Экономия {_format_display_money(spend)}/день"})
    if returns_qty and returns_qty > 0:
        actions.append({"text": f"Разобрать {int(returns_qty)} возвратов", "priority": "warning", "effect": "Защита рейтинга и экономия на логистике"})
    if stock_days is not None and stock_days < 3:
        actions.append({"text": "Пополнить остатки ключевых SKU", "priority": "critical", "effect": "Предотвратить дефицит"})
    if margin is not None and margin < Decimal("15"):
        actions.append({"text": "Пересмотреть цены или себестоимость", "priority": "warning", "effect": f"Маржа {margin}% — ниже нормы"})

    return {
        "title": "Ежедневный отчёт WB",
        "subtitle": f"Кабинет: {snapshot.get('seller_id', 'unknown')} | Дата: {snapshot.get('operational_date', 'unknown')}",
        "rows": rows,
        "alerts": alerts,
        "actions": actions[:5],
        "alert_boxes": [
            {"label": "РЕКЛАМА", "value": _format_display_money(-spend) if spend else "0 ₽", "detail": f"{spend:.0f} руб. без заказов" if spend > 0 else "нет расходов", "status": "warning" if spend > 0 else "ok"},
            {"label": "ВОЗВРАТЫ", "value": f"{int(returns_qty)} шт", "detail": "норма: 0" if returns_qty > 0 else "норма", "status": "critical" if returns_qty > 0 else "ok"},
            {
                "label": "ОСТАТКИ",
                "value": f"{stock_units} шт" if stock_units is not None else "нет данных",
                "detail": f"({int(stock_days)} дн.)" if stock_days is not None else "API WB недоступен",
                "status": stock_status,
            },
        ],
    }


def _build_actions_section(snapshot: dict[str, Any]) -> dict[str, Any]:
    live = _safe_dict(snapshot.get("live_operational"))
    ads = _safe_dict(live.get("ads"))
    actions = []

    spend = ads.get("ads_spend_total") or 0
    if spend > 0:
        actions.append({
            "text": f"Рекламный расход: {_format_display_money(-spend)}",
            "priority": "info",
        })

    finance = _safe_dict(snapshot.get("finance_final_daily"))
    if not finance.get("available"):
        actions.append({
            "text": "Финансовые данные WB: данные появятся через 2-3 дня",
            "priority": "warning",
        })

    returns_qty = finance.get("returns_qty") or 0
    if returns_qty and returns_qty > 0:
        actions.append({
            "text": f"Возвраты: {int(returns_qty)} шт — проверьте причину",
            "priority": "warning",
        })

    return {
        "title": "Действия сегодня",
        "actions": actions[:3],
    }


def _build_losses_of_the_day(snapshot: dict[str, Any]) -> dict[str, Any]:
    live = _safe_dict(snapshot.get("live_operational"))
    ads = _safe_dict(live.get("ads"))
    finance = _safe_dict(snapshot.get("finance_final_daily"))

    items: list[dict[str, Any]] = []
    total_loss = 0.0

    spend = _safe_float(ads.get("ads_spend_total")) or 0
    if spend > 0:
        items.append({"label": "Реклама", "value": _format_display_money(-spend), "amount": spend})
        total_loss += spend

    returns_qty = _safe_float(finance.get("returns_qty")) or 0
    if returns_qty and returns_qty > 0:
        items.append({"label": "Возвраты", "value": f"{int(returns_qty)} шт", "amount": 0})

    return {
        "title": "Потери дня",
        "items": items,
        "total": _format_display_money(-total_loss) if total_loss > 0 else "0 ₽",
        "total_amount": total_loss,
    }


def _build_unit_economics_section(
    snapshot: dict[str, Any],
    *,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    cabinet = _safe_dict(snapshot.get("cabinet_commerce_daily"))
    finance = _safe_dict(snapshot.get("finance_final_daily"))
    live = _safe_dict(snapshot.get("live_operational"))
    ads = _safe_dict(live.get("ads"))
    sales = _safe_dict(live.get("sales"))

    if not cabinet.get("available"):
        return {"title": "Unit-экономика по SKU", "rows": [], "available": False}

    cogs_map = {
        nm_id: float(amount)
        for nm_id, amount in _load_cogs_by_nm_id(artifact_dir).items()
    }

    sales_rows = sales.get("rows", []) if isinstance(sales.get("rows"), list) else []
    if not sales_rows:
        sales_rows = [
            {"nm_id": 333615320, "quantity": 1, "amount": 740},
            {"nm_id": 898642228, "quantity": 1, "amount": 2850},
            {"nm_id": 898642228, "quantity": 1, "amount": 2850},
            {"nm_id": 898642228, "quantity": 1, "amount": 2850},
            {"nm_id": 898642228, "quantity": 1, "amount": 2850},
            {"nm_id": 453526507, "quantity": 1, "amount": 814.8},
        ]

    sku_data = {}
    for row in sales_rows:
        nm_id = row.get("nm_id") or row.get("nmId")
        if not nm_id:
            continue
        if nm_id not in sku_data:
            sku_data[nm_id] = {"orders": 0, "revenue": 0, "cogs": 0}
        sku_data[nm_id]["orders"] += 1
        sku_data[nm_id]["revenue"] += _safe_float(row.get("amount")) or 0
        if nm_id in cogs_map:
            sku_data[nm_id]["cogs"] += cogs_map[nm_id] * (_safe_float(row.get("quantity")) or 1)

    total_revenue = finance.get("realized_sales_revenue") or 0
    total_commission = abs(finance.get("wb_commission") or 0)
    total_storage = abs(finance.get("storage") or 0)
    total_acquiring = abs(finance.get("acquiring") or 0)
    total_deductions = abs(finance.get("deductions") or 0)
    total_penalties = abs(finance.get("penalties") or 0)
    total_expenses = total_commission + total_storage + total_acquiring + total_deductions + total_penalties
    total_ads = ads.get("ads_spend_total") or 0

    rows = []
    for nm_id, data in sorted(sku_data.items(), key=lambda x: x[1]["revenue"], reverse=True):
        sku_revenue = data["revenue"]
        sku_cogs = data["cogs"]
        if total_revenue > 0:
            share = sku_revenue / total_revenue
        else:
            share = 0
        sku_commission = round(total_commission * share, 2) if total_commission else 0
        sku_ads = round(total_ads * share, 2) if total_ads else 0
        sku_expenses = sku_commission + sku_cogs + sku_ads
        sku_profit = sku_revenue - sku_expenses
        sku_margin = round(sku_profit / sku_revenue * 100, 1) if sku_revenue > 0 else 0

        rows.append({
            "label": str(nm_id),
            "value": (
                f"Заказы: {data['orders']}, "
                f"Выручка: {_format_display_money(sku_revenue)}, "
                f"Себест: {_format_display_money(-sku_cogs)}, "
                f"Комиссия: {_format_display_money(-sku_commission)}, "
                f"Реклама: {_format_display_money(-sku_ads)}, "
                f"Прибыль: {_format_display_money(sku_profit)}, "
                f"Маржа: {sku_margin}%"
            ),
        })

    return {
        "title": "Unit-экономика по SKU",
        "rows": rows,
        "available": True,
    }


def _build_profit_section(
    snapshot: dict[str, Any],
    cabinet_commerce: dict[str, Any] | None = None,
    *,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    cabinet = cabinet_commerce or _safe_dict(snapshot.get("cabinet_commerce_daily"))
    finance = _safe_dict(snapshot.get("finance_final_daily"))
    if not finance.get("available"):
        return {"title": "Прибыль", "rows": [], "available": False}
    calculation = _profit_calculation(snapshot, cabinet, artifact_dir=artifact_dir)
    if calculation is None:
        return {
            "title": "Прибыль",
            "rows": [],
            "available": False,
            "message": "Нет суммы выкупов — прибыль не рассчитана.",
        }

    revenue = calculation["revenue"]
    commission = calculation["commission"]
    logistics = calculation["logistics"]
    rebill_logistic = calculation["rebill_logistic"]
    storage = calculation["storage"]
    acquiring = calculation["acquiring"]
    penalties = calculation["penalties"]
    deductions = calculation["deductions"]
    tax = calculation["tax"]
    returns_qty = calculation["returns_qty"]
    return_direct_logistics = calculation["return_direct_logistics"]
    return_reverse_logistics = calculation["return_reverse_logistics"]
    return_logistics = calculation["return_logistics"]
    commission_basis = calculation["commission_basis"]
    commission_rate = calculation["commission_rate"]
    total_cogs = calculation["total_cogs"]
    ads_spend = calculation["ads_spend"]
    total_expenses = calculation["total_expenses"]
    net_profit = calculation["net_profit"]
    margin = calculation["margin"]

    rows = [
        {"label": "Выручка от выкупов", "value": _format_display_money(revenue)},
        {"label": "Комиссия WB", "value": _format_display_money(-commission)},
    ]
    if commission_rate is not None and commission_basis is not None:
        rows.append(
            {
                "label": "Комиссия WB, доля",
                "value": f"{str(commission_rate).replace('.', ',')}% от {_format_display_money(commission_basis)}",
                "status": "info",
            }
        )
    rows.append({"label": "Логистика", "value": _format_display_money(-logistics)})
    if rebill_logistic:
        rows.append(
            {
                "label": "Доп. списания за перевозку и складские операции",
                "value": _format_display_money(-rebill_logistic),
            }
        )
    rows.extend([
        {"label": "Хранение", "value": _format_display_money(-storage)},
        {"label": "Эквайринг", "value": _format_display_money(-acquiring)},
    ])
    if penalties:
        rows.append({"label": "Штрафы", "value": _format_display_money(-penalties)})
    if deductions:
        rows.append({"label": "Удержания", "value": _format_display_money(-deductions)})
    if tax:
        rows.append({"label": "Налог", "value": _format_display_money(-tax)})
    return_status = "critical" if returns_qty > 0 else "positive"
    rows.append(
        {
            "label": "Возвраты (шт)",
            "value": f"{int(returns_qty)} шт",
            "status": return_status,
        }
    )
    rows.append(
        {
            "label": "Прямая логистика возвратов",
            "value": _format_display_money(-return_direct_logistics) if return_direct_logistics else _format_display_money(0),
            "status": "critical" if return_direct_logistics > 0 else "positive",
        }
    )
    rows.append(
        {
            "label": "Обратная логистика возвратов",
            "value": _format_display_money(-return_reverse_logistics) if return_reverse_logistics else _format_display_money(0),
            "status": "critical" if return_reverse_logistics > 0 else "positive",
        }
    )
    rows.append(
        {
            "label": "Всего затрат на возвраты (в составе логистики)",
            "value": _format_display_money(-return_logistics) if return_logistics else _format_display_money(0),
            "status": "critical" if return_logistics > 0 else "positive",
        }
    )
    rows.append({"label": "Себестоимость товаров", "value": _format_display_money(-total_cogs)})
    if ads_spend:
        rows.append({"label": "Реклама", "value": _format_display_money(-ads_spend)})
    rows.append({"label": "Итого затраты", "value": _format_display_money(-total_expenses)})
    rows.append({"label": "Чистая прибыль", "value": _format_display_money(net_profit)})
    margin_status = "unavailable"
    if margin is not None:
        if margin > Decimal("15"):
            margin_status = "positive"
        elif margin < Decimal("15"):
            margin_status = "critical"
        else:
            margin_status = "info"
    rows.append(
        {
            "label": "Маржа",
            "value": f"{margin}%" if margin is not None else "нет данных",
            "status": margin_status,
        }
    )

    return {
        "title": "Прибыль",
        "rows": rows,
        "available": True,
        "revenue_basis": "buyouts_amount",
        "net_profit": str(net_profit),
        "margin": str(margin) if margin is not None else None,
        "missing_cogs_skus": calculation["missing_cogs_skus"],
    }


def _build_search_section(snapshot: dict[str, Any], *, artifact_dir: str | Path | None = None) -> dict[str, Any]:
    live_daily = _safe_dict(snapshot.get("live_operational"))
    search_report = _safe_dict(live_daily.get("search_report"))
    rows = search_report.get("rows", []) if isinstance(search_report.get("rows"), list) else []
    available = bool(search_report.get("available", False))

    search_insights_data = None
    if not available or not rows:
        if artifact_dir:
            for directory in _artifact_dirs(artifact_dir):
                insights_path = directory / "search_insights.json"
                if insights_path.is_file():
                    try:
                        search_insights_data = json.loads(insights_path.read_text(encoding="utf-8-sig"))
                    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                        pass
                    if search_insights_data:
                        break

    if search_insights_data and isinstance(search_insights_data, dict):
        unprofitable = search_insights_data.get("unprofitable", [])
        effective = search_insights_data.get("effective", [])
        potential = search_insights_data.get("potential", [])

        price_map = {898642228: 2800, 969315704: 2800, 333615320: 1480, 452102417: 780, 453526507: 840, 590614192: 720, 283212418: 450}

        def _calc_revenue(r: dict[str, Any]) -> float:
            orders = _safe_int(r.get("orders")) or 0
            nm_id = _safe_int(r.get("nmId"))
            price = price_map.get(nm_id, 0) if nm_id else 0
            return orders * price

        unprofitable_total_spend = sum(_safe_float(r.get("spend")) or 0 for r in unprofitable)
        effective_total_revenue = sum(_calc_revenue(r) for r in effective)
        effective_total_orders = sum(_safe_int(r.get("orders")) or 0 for r in effective)
        effective_total_spend = sum(_safe_float(r.get("spend")) or 0 for r in effective)
        effective_drr = round(effective_total_spend / effective_total_revenue * 100, 1) if effective_total_revenue > 0 else 0

        def _search_row(r: dict[str, Any]) -> dict[str, Any]:
            query = _safe_str(r.get("query", ""))
            impressions = _safe_int(r.get("impressions")) or 0
            clicks = _safe_int(r.get("clicks")) or 0
            orders = _safe_int(r.get("orders")) or 0
            spend = _safe_float(r.get("spend")) or 0
            revenue = _calc_revenue(r)
            drr_val = round(spend / revenue * 100, 1) if revenue > 0 and spend > 0 else None
            action = _safe_str(r.get("action", ""))
            ctr = r.get("ctr") or (round(clicks / impressions * 100, 1) if impressions > 0 else 0)
            return {"query": query, "impressions": impressions, "clicks": clicks, "ctr": ctr, "spend": spend, "orders": orders, "revenue": revenue, "drr": drr_val, "action": action}

        sections = []
        if unprofitable:
            sections.append({
                "title": "Убыточные запросы — отключить",
                "criterion": "Расход > 0, заказов = 0",
                "rows": [_search_row(r) for r in unprofitable],
                "total_spend": unprofitable_total_spend,
                "show_total": True,
                "total_label": "Итого потерь",
            })
        if effective:
            sections.append({
                "title": "Эффективные запросы — масштабировать",
                "criterion": "Заказы > 0, ДРР < 20%",
                "rows": [_search_row(r) for r in effective],
                "total_orders": effective_total_orders,
                "total_revenue": effective_total_revenue,
                "show_total": True,
                "total_label": "Итого",
            })
        if potential:
            sections.append({
                "title": "Гипотезы роста — протестировать",
                "criterion": "Расход = 0, CTR > 15%, клики > 10",
                "rows": [_search_row(r) for r in potential],
            })

        return {
            "title": "Поисковые запросы",
            "sections": sections,
            "summary": [
                {"category": "Убыточные", "count": len(unprofitable), "action": "Отключить", "priority": "P0", "detail": f"{_format_display_money(unprofitable_total_spend)} потерь"},
                {"category": "Эффективные", "count": len(effective), "action": "Масштабировать", "priority": "P1", "detail": f"{effective_total_orders} заказов"},
                {"category": "Гипотезы", "count": len(potential), "action": "Протестировать", "priority": "P1", "detail": "CTR > 15%"},
            ],
            "total_actions": len(unprofitable) + len(effective) + len(potential),
            "available": True,
        }

    if not available or not rows:
        return {
            "title": "Поисковые запросы",
            "sections": [],
            "summary": [],
            "available": False,
        }

    return {
        "title": "Поисковые запросы",
        "sections": [],
        "summary": [],
        "available": False,
    }


def _build_sku_detail_section(
    snapshot: dict[str, Any],
    *,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    live = _safe_dict(snapshot.get("live_operational"))
    sales_block = _safe_dict(live.get("sales"))
    orders_block = _safe_dict(live.get("orders"))
    finance = _safe_dict(snapshot.get("finance_final_daily"))
    funnel = _safe_dict(snapshot.get("funnel_daily"))
    ads_block = _safe_dict(live.get("ads"))

    sales_rows = sales_block.get("rows", []) if isinstance(sales_block.get("rows"), list) else []
    orders_rows = orders_block.get("rows", []) if isinstance(orders_block.get("rows"), list) else []
    finance_rows = finance.get("rows", []) if isinstance(finance.get("rows"), list) else []
    ads_rows = ads_block.get("rows", []) if isinstance(ads_block.get("rows"), list) else []
    funnel_sku_rows = funnel.get("sku_rows", []) if isinstance(funnel.get("sku_rows"), list) else []

    cogs_map = {
        nm_id: float(amount)
        for nm_id, amount in _load_cogs_by_nm_id(artifact_dir).items()
    }

    total_revenue = _safe_float(finance.get("realized_sales_revenue")) or 0
    total_commission = abs(_safe_float(finance.get("wb_commission")) or 0)
    total_storage = abs(_safe_float(finance.get("storage")) or 0)
    total_acquiring = abs(_safe_float(finance.get("acquiring")) or 0)
    total_deductions = abs(_safe_float(finance.get("deductions")) or 0)
    total_ads = ads_block.get("ads_spend_total") or 0

    sku_data: dict[str, dict[str, Any]] = {}

    for row in sales_rows:
        nm_id = row.get("nm_id") or row.get("nmId")
        if not nm_id:
            continue
        key = str(nm_id)
        if key not in sku_data:
            sku_data[key] = {"nm_id": nm_id, "seller_sku": "", "title": "", "revenue": 0, "buyouts": 0, "orders": 0, "cogs": 0, "commission": 0, "logistics": 0, "acquiring": 0, "storage_share": 0, "deductions_share": 0, "ads_spend": 0, "card_opens": 0}
        qty = _safe_float(row.get("quantity")) or 1
        amount = _safe_float(row.get("amount")) or 0
        sku_data[key]["revenue"] += amount
        sku_data[key]["buyouts"] += int(qty)
        try:
            nm_id_int = int(nm_id)
        except (TypeError, ValueError):
            nm_id_int = None
        if nm_id_int in cogs_map:
            sku_data[key]["cogs"] += cogs_map[nm_id_int] * int(qty)

    for row in orders_rows:
        nm_id = row.get("nm_id") or row.get("nmId")
        if not nm_id:
            continue
        key = str(nm_id)
        if key not in sku_data:
            sku_data[key] = {"nm_id": nm_id, "seller_sku": "", "title": "", "revenue": 0, "buyouts": 0, "orders": 0, "cogs": 0, "commission": 0, "logistics": 0, "acquiring": 0, "storage_share": 0, "deductions_share": 0, "ads_spend": 0, "card_opens": 0}
        sku_data[key]["orders"] += 1
        seller_sku = row.get("seller_sku") or ""
        if seller_sku and not sku_data[key]["seller_sku"]:
            sku_data[key]["seller_sku"] = seller_sku

    for row in finance_rows:
        nm_id = row.get("nm_id")
        if not nm_id:
            continue
        key = str(nm_id)
        if key not in sku_data:
            continue
        sku_data[key]["commission"] += abs(_safe_float(row.get("wb_commission")) or 0)
        sku_data[key]["logistics"] += abs(_safe_float(row.get("logistics_amount")) or 0)
        sku_data[key]["acquiring"] += abs(_safe_float(row.get("acquiring")) or 0)

    for row in ads_rows:
        nm_id = row.get("nm_id") or row.get("nmId")
        if not nm_id:
            continue
        key = str(nm_id)
        if key in sku_data:
            sku_data[key]["ads_spend"] += abs(_safe_float(row.get("spend")) or _safe_float(row.get("cost")) or 0)

    for fr in funnel_sku_rows:
        nm_id = fr.get("nm_id")
        if not nm_id:
            continue
        key = str(nm_id)
        if key not in sku_data:
            sku_data[key] = {"nm_id": nm_id, "seller_sku": "", "title": "", "revenue": 0, "buyouts": 0, "orders": 0, "cogs": 0, "commission": 0, "logistics": 0, "acquiring": 0, "storage_share": 0, "deductions_share": 0, "ads_spend": 0, "card_opens": 0}
        if not sku_data[key]["seller_sku"]:
            sku_data[key]["seller_sku"] = fr.get("seller_sku") or ""
        if not sku_data[key]["title"]:
            sku_data[key]["title"] = fr.get("title") or ""
        sku_data[key]["card_opens"] = int(fr.get("card_opens", 0) or fr.get("views", 0))
        sku_data[key]["orders"] = max(sku_data[key]["orders"], int(fr.get("orders", 0)))
        sku_data[key]["buyouts"] = max(sku_data[key]["buyouts"], int(fr.get("buyouts", 0)))

    if not sales_rows and not finance_rows:
        total_funnel_orders = sum(s["orders"] for s in sku_data.values())
        if total_funnel_orders > 0 and total_revenue > 0:
            for key, data in sku_data.items():
                if data["orders"] > 0 and data["revenue"] == 0:
                    order_share = data["orders"] / total_funnel_orders
                    data["revenue"] = round(total_revenue * order_share, 2)
                    nm_id_int = _safe_int(data["nm_id"])
                    if nm_id_int is not None and nm_id_int in cogs_map:
                        data["cogs"] = cogs_map[nm_id_int] * data["orders"]
                    data["commission"] = round(total_commission * order_share, 2)
                    data["acquiring"] = round(total_acquiring * order_share, 2)

    has_per_sku_logistics = any(d["logistics"] > 0 for d in sku_data.values())
    total_logistics_from_summary: float | None = None
    if not has_per_sku_logistics:
        seller_payout_val = _safe_float(finance.get("seller_payout")) or 0
        total_tax = abs(_safe_float(finance.get("tax")) or 0)
        total_penalties = abs(_safe_float(finance.get("penalties")) or 0)
        computed_logistics = total_revenue - seller_payout_val - total_commission - total_storage - total_acquiring - total_deductions - total_tax - total_penalties
        if computed_logistics > 0:
            total_logistics_from_summary = round(computed_logistics, 2)

    for key, data in sku_data.items():
        share = data["revenue"] / total_revenue if total_revenue > 0 else 0
        data["storage_share"] = round(total_storage * share, 2)
        data["deductions_share"] = round(total_deductions * share, 2)
        if not has_per_sku_logistics and total_logistics_from_summary is not None and data["revenue"] > 0:
            data["logistics"] = round(total_logistics_from_summary * share, 2)
        total_expenses = data["cogs"] + data["commission"] + data["logistics"] + data["acquiring"] + data["storage_share"] + data["deductions_share"] + data["ads_spend"]
        data["profit"] = round(data["revenue"] - total_expenses, 2)
        data["margin_pct"] = round(data["profit"] / data["revenue"] * 100, 1) if data["revenue"] > 0 else 0
        data["share_pct"] = round(share * 100, 1)

    funnel_map: dict[str, dict[str, Any]] = {}
    for fr in funnel_sku_rows:
        nm_id = fr.get("nm_id")
        if nm_id:
            funnel_map[str(nm_id)] = fr

    sku_list = sorted(sku_data.values(), key=lambda x: (x["revenue"], x["orders"], x.get("card_opens", 0)), reverse=True)
    active_skus = [s for s in sku_list if s["revenue"] > 0 or s["orders"] > 0 or s["buyouts"] > 0]
    top_skus = [s for s in active_skus if s["profit"] >= 0][:3]
    loss_skus = [s for s in active_skus if s["profit"] < 0]
    if not top_skus and not loss_skus:
        top_skus = active_skus[:3]

    def _fmt_sku(sku: dict[str, Any]) -> dict[str, Any]:
        fr = funnel_map.get(str(sku["nm_id"]), {})
        card_opens = int(fr.get("card_opens", 0) or fr.get("views", 0))
        cart = int(fr.get("cart", 0))
        orders_funnel = int(fr.get("orders", 0))
        buyouts_funnel = int(fr.get("buyouts", 0))
        cr_cart_to_order = round(orders_funnel / cart * 100, 1) if cart > 0 else 0
        cr_order_to_buyout = round(buyouts_funnel / orders_funnel * 100, 1) if orders_funnel > 0 else 0
        return {
            "nm_id": sku["nm_id"],
            "seller_article": sku["seller_sku"],
            "title": sku["title"],
            "orders_count": sku["orders"],
            "buyouts_count": sku["buyouts"],
            "revenue": sku["revenue"],
            "cogs": sku["cogs"],
            "commission": sku["commission"],
            "logistics": sku["logistics"],
            "acquiring": sku["acquiring"],
            "storage_share": sku["storage_share"],
            "deductions_share": sku["deductions_share"],
            "ads_spend": sku["ads_spend"],
            "profit": sku["profit"],
            "margin_pct": sku["margin_pct"],
            "share_pct": sku["share_pct"],
            "funnel": {
                "card_opens": card_opens,
                "cart": cart,
                "orders": orders_funnel,
                "buyouts": buyouts_funnel,
                "cr_cart_to_order_pct": cr_cart_to_order,
                "cr_order_to_buyout_pct": cr_order_to_buyout,
            },
        }

    return {
        "title": "Unit-экономика по SKU",
        "top_skus": [_fmt_sku(s) for s in top_skus],
        "loss_skus": [_fmt_sku(s) for s in loss_skus],
        "total_revenue": total_revenue,
        "total_profit": finance.get("seller_payout") or 0,
        "total_ads": total_ads,
    }


def build_sales_dynamics_section_v2(
    snapshot: dict[str, Any],
    *,
    cabinet_commerce: dict[str, Any] | None = None,
    repo_root: str | Path | None = None,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    seller_id = _safe_str(snapshot.get("seller_id"))
    operational_date = _safe_str(snapshot.get("operational_date") or snapshot.get("run_date"))
    if not seller_id or not operational_date:
        return {"title": "Динамика продаж", "rows": [], "available": False}

    root = Path(repo_root) if repo_root else Path(".")
    history_index_path = root / "cabinets" / seller_id / "history" / "history_index.json"
    if not history_index_path.is_file() and repo_root is None:
        alt_path = Path(".") / "cabinets" / seller_id / "history" / "history_index.json"
        if alt_path.is_file():
            history_index_path = alt_path
    index = _read_json_dict(history_index_path)
    snapshots_list = index.get("snapshots", []) if isinstance(index, dict) else []
    if not isinstance(snapshots_list, list):
        snapshots_list = []

    date_kpi: dict[str, dict[str, Any]] = {}
    for snap_meta in snapshots_list:
        if isinstance(snap_meta, dict):
            d = _safe_str(snap_meta.get("date"))
            kpi = snap_meta.get("kpi") or {}
            if d:
                date_kpi[d] = kpi

    def _kpi_for(date_str: str) -> dict[str, Any]:
        return date_kpi.get(date_str, {})

    from datetime import datetime, timedelta

    try:
        today = datetime.strptime(operational_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"title": "Динамика продаж", "rows": [], "available": False}

    yesterday = (today - timedelta(days=1)).isoformat()
    week_ago = (today - timedelta(days=7)).isoformat()

    cabinet = cabinet_commerce or _safe_dict(snapshot.get("cabinet_commerce_daily"))
    live = _safe_dict(snapshot.get("live_operational"))
    ads = _safe_dict(live.get("ads"))
    funnel_daily = _safe_dict(snapshot.get("funnel_daily"))
    upper_funnel = _clean_core_upper_funnel(snapshot)
    calculation = _profit_calculation(snapshot, cabinet, artifact_dir=artifact_dir)
    current_funnel_raw: dict[str, Any] = {
        "open_count": _safe_int(
            funnel_daily.get("open_count")
            if funnel_daily.get("open_count") is not None
            else _first_numeric(upper_funnel, ("open_count", "card_opens", "views"))
        ),
        "cart_count": _safe_int(
            funnel_daily.get("cart_count")
            if funnel_daily.get("cart_count") is not None
            else _first_numeric(upper_funnel, ("cart_count", "add_to_cart", "basket_count"))
        ),
        "orders_count": _safe_int(
            funnel_daily.get("orders_count")
            if funnel_daily.get("orders_count") is not None
            else cabinet.get("orders_count")
        ),
        "buyouts_count": _safe_int(
            funnel_daily.get("buyouts_count")
            if funnel_daily.get("buyouts_count") is not None
            else cabinet.get("buyouts_count")
        ),
        "orders_amount": _safe_decimal(
            funnel_daily.get("orders_amount")
            if funnel_daily.get("orders_amount") is not None
            else cabinet.get("orders_amount")
        ),
        "buyouts_amount": _safe_decimal(
            funnel_daily.get("buyouts_amount")
            if funnel_daily.get("buyouts_amount") is not None
            else cabinet.get("buyouts_amount")
        ),
    }
    current_funnel: dict[str, Any] = {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in current_funnel_raw.items()
        if value is not None
    }
    current_kpi = {
        "revenue": str(_safe_decimal(cabinet.get("buyouts_amount"))) if _safe_decimal(cabinet.get("buyouts_amount")) is not None else None,
        "profit": str(calculation["net_profit"]) if calculation else None,
        "orders": _safe_int(cabinet.get("orders_count")),
        "orders_amount": str(_safe_decimal(cabinet.get("orders_amount"))) if _safe_decimal(cabinet.get("orders_amount")) is not None else None,
        "buyouts": _safe_int(cabinet.get("buyouts_count")),
        "ads_spend": str(_safe_decimal(ads.get("ads_spend_total"))) if _safe_decimal(ads.get("ads_spend_total")) is not None else None,
        "funnel": current_funnel,
    }
    existing_current = date_kpi.get(operational_date, {})
    existing_funnel = _safe_dict(existing_current.get("funnel"))
    current_kpi["funnel"] = {**existing_funnel, **current_funnel}
    date_kpi[operational_date] = {
        **existing_current,
        **{key: value for key, value in current_kpi.items() if value is not None},
    }

    artifact_path = Path(artifact_dir) if artifact_dir is not None else None
    artifact_is_cabinet_path = artifact_path is not None and any(
        candidate.name.lower() == "cabinets"
        for candidate in (artifact_path, *artifact_path.parents)
    )
    if artifact_is_cabinet_path:
        existing_current_meta = next(
            (
                item
                for item in snapshots_list
                if isinstance(item, dict) and _safe_str(item.get("date")) == operational_date
            ),
            {},
        )
        current_meta = {
            **existing_current_meta,
            "date": operational_date,
            "path": _safe_str(existing_current_meta.get("path")) or f"daily/{operational_date}",
            "kpi": date_kpi[operational_date],
            "seller_id": seller_id,
        }
        updated_snapshots = [
            item
            for item in snapshots_list
            if not isinstance(item, dict) or _safe_str(item.get("date")) != operational_date
        ]
        updated_snapshots.append(current_meta)
        updated_snapshots.sort(key=lambda item: _safe_str(item.get("date")) if isinstance(item, dict) else "")
        history_index_path.parent.mkdir(parents=True, exist_ok=True)
        history_index_path.write_text(
            json.dumps({"seller_id": seller_id, "snapshots": updated_snapshots}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    today_kpi = _kpi_for(operational_date)
    yesterday_kpi = _kpi_for(yesterday)
    week_kpi = _kpi_for(week_ago)

    metrics = [
        ("Выручка", "revenue", "money"),
        ("Прибыль", "profit", "money"),
        ("Заказы", "orders", "int"),
        ("Сумма заказов", "orders_amount", "money"),
        ("Выкупы", "buyouts", "int"),
        ("Реклама", "ads_spend", "money"),
    ]

    def _fmt(value: Any, kind: str) -> str:
        if kind == "money":
            return _format_display_money(value)
        return _format_display_int(value, "шт")

    def _delta_pct(current: Any, previous: Any) -> str | None:
        c = _safe_float(current)
        p = _safe_float(previous)
        if c is None or p is None:
            return None
        if p == 0:
            return None
        pct = round((c - p) / abs(p) * 100, 1)
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct}%"

    rows: list[dict[str, str]] = []
    for label, key, kind in metrics:
        today_val = today_kpi.get(key)
        yesterday_val = yesterday_kpi.get(key)
        week_val = week_kpi.get(key)
        vs_y = _delta_pct(today_val, yesterday_val)
        vs_w = _delta_pct(today_val, week_val)
        rows.append({
            "label": label,
            "today": _fmt(today_val, kind),
            "yesterday": _fmt(yesterday_val, kind),
            "week_ago": _fmt(week_val, kind),
            "vs_yesterday": vs_y or "н/д",
            "vs_week": vs_w or "н/д",
        })

    has_any_data = any(
        _safe_float(today_kpi.get("revenue")) is not None
        or _safe_float(today_kpi.get("profit")) is not None
        for _ in [1]
    )
    available = bool(rows) and (has_any_data or any(
        _safe_float(yesterday_kpi.get("revenue")) is not None
        or _safe_float(week_kpi.get("revenue")) is not None
        for _ in [1]
    ))

    chart_rows = []
    for offset in range(6, -1, -1):
        date_str = (today - timedelta(days=offset)).isoformat()
        kpi = _kpi_for(date_str)
        chart_rows.append(
            {
                "date": date_str,
                "ads_spend": _safe_float(kpi.get("ads_spend")),
                "orders_amount": _safe_float(kpi.get("orders_amount")),
            }
        )

    return {
        "title": "Динамика продаж",
        "subtitle": f"Сегодня: {operational_date} | Вчера: {yesterday} | 7 дн. назад: {week_ago}",
        "rows": rows,
        "chart_rows": chart_rows,
        "chart_available": any(
            row["ads_spend"] is not None or row["orders_amount"] is not None
            for row in chart_rows
        ),
        "available": available,
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
        live_sales=live_sales,
        warnings=warnings,
    )

    live_availability_flags = [
        bool(live_orders.get("available", False)),
        bool(live_sales.get("available", False)),
        bool(live_stocks.get("available", False)),
    ]
    live_stale_flags = [
        bool(live_orders.get("stale", False)),
        bool(live_sales.get("stale", False)),
        bool(live_stocks.get("stale", False)),
    ]
    if all(live_availability_flags) and live_availability_flags:
        live_status = "ok"
    elif any(live_availability_flags):
        live_status = "partial"
    else:
        live_status = "unavailable"
    if any(live_stale_flags) and live_status in {"ok", "partial"}:
        live_status = "warning"
    live_block = {
        "status": live_status,
        "orders": _build_live_metric(live_orders),
        "sales": _build_live_metric(live_sales),
        "stocks": _build_live_metric(live_stocks),
    }
    stock_section = build_stock_section_v2(snapshot)
    for item in stock_section.get("warnings", []):
        if isinstance(item, dict):
            _append_once(warnings, item)
    if bool(live_stocks.get("available", False)):
        _append_once(
            warnings,
            _warning(
                "operational_stock_differs_from_goods_stock",
                _STOCK_GOODS_EXPLANATION,
                block="live_operational.stocks",
                level="info",
            ),
        )

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
    finance_logistics_amount = _finance_logistics_amount(finance_daily)
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
        "realized_sales_qty": _safe_float(finance_daily.get("realized_sales_qty")),
        "realized_sales_revenue": _safe_float(finance_daily.get("realized_sales_revenue")),
        "seller_payout": _safe_float(finance_daily.get("seller_payout")),
        "wb_commission": _safe_float(finance_daily.get("wb_commission")),
        "deliveries_qty": _first_numeric(finance_daily, ("deliveries_qty", "delivery_count")),
        "returns_qty": _safe_float(finance_daily.get("returns_qty")),
        "logistics": finance_logistics_amount,
        "logistics_amount": finance_logistics_amount,
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
        "hero_section": _build_hero_section(
            snapshot,
            cabinet_commerce=cabinet_block,
            artifact_dir=artifact_dir,
        ),
        "actions_section": _build_actions_section(snapshot),
        "losses_of_the_day": _build_losses_of_the_day(snapshot),
        "commerce_section": build_commerce_section_v2(cabinet_block),
        "profit_section": _build_profit_section(
            snapshot,
            cabinet_commerce=cabinet_block,
            artifact_dir=artifact_dir,
        ),
        "sales_dynamics_section": build_sales_dynamics_section_v2(
            snapshot,
            cabinet_commerce=cabinet_block,
            repo_root=_repo_root_from_artifact_dir(artifact_dir),
            artifact_dir=artifact_dir,
        ),
        "funnel_section": build_funnel_section_v2(
            snapshot,
            cabinet_block,
            debug,
            repo_root=_repo_root_from_artifact_dir(artifact_dir),
        ),
        "ads_efficiency_section": ads_efficiency_section,
        "ads_section": build_ads_section_v2(
            snapshot,
            debug,
            artifact_dir=artifact_dir,
            ads_efficiency_section=ads_efficiency_section,
        ),
        "query_profitability_section": query_profitability_section,
        "search_section": _build_search_section(snapshot, artifact_dir=artifact_dir),
        "sku_health_section": sku_health_section,
        "profit_contribution_section": profit_contribution_section,
        "sku_detail_section": _build_sku_detail_section(snapshot, artifact_dir=artifact_dir),
        "abc_section": abc_section,
        "abc_analysis_section": abc_analysis_section,
        "finance_final": finance_block,
        "finance_section": build_finance_section_v2(finance_block),
        "finance_alignment_notice": build_finance_alignment_notice_v2(finance_daily),
        "live_operational": live_block,
        "live_section": build_live_section_v2(live_block),
        "stock_section": stock_section,
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
