from __future__ import annotations

from typing import Any

from ..contracts.report_payload_schema import (
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
    ReportPayloadV2,
    SectionV2,
    SourceFlagRowV2,
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

    orders_status = "ok" if cabinet_available and cabinet.get("orders_count") is not None else "unavailable"
    buyouts_status = "ok" if cabinet_available and cabinet.get("buyouts_count") is not None else "unavailable"
    payout_status = "unavailable"
    if finance_available and finance.get("seller_payout") is not None:
        payout_status = "warning" if finance_status == "lagged" else "ok"
    stocks_status = "ok" if stocks_available and stocks.get("total_units") is not None else "unavailable"

    cards: list[HeroKpiCardV2] = [
        {
            "label": "Заказы",
            "value": _format_hero_int(cabinet.get("orders_count"), "шт"),
            "subvalue": _format_hero_money(cabinet.get("orders_amount")),
            "status": orders_status,
        },
        {
            "label": "Выкупы",
            "value": _format_hero_int(cabinet.get("buyouts_count"), "шт"),
            "subvalue": _format_hero_money(cabinet.get("buyouts_amount")),
            "status": buyouts_status,
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
    owner = _format_display_text(commerce.get("owner_block"))
    target_date = _format_display_text(commerce.get("target_date"))
    status = "ok" if available else "unavailable"

    rows: list[DisplayRowV2] = [
        _display_row(
            "Заказы",
            _format_display_int(commerce.get("orders_count"), "шт"),
            note=f"Дата: {target_date}",
            status=_display_status(available, commerce.get("orders_count")),
        ),
        _display_row(
            "Сумма заказов",
            _format_display_money(commerce.get("orders_amount")),
            note=f"Источник: {source}",
            status=_display_status(available, commerce.get("orders_amount")),
        ),
        _display_row(
            "Выкупы",
            _format_display_int(commerce.get("buyouts_count"), "шт"),
            note=f"Владелец: {owner}",
            status=_display_status(available, commerce.get("buyouts_count")),
        ),
        _display_row(
            "Сумма выкупов",
            _format_display_money(commerce.get("buyouts_amount")),
            note=f"Источник: {source}",
            status=_display_status(available, commerce.get("buyouts_amount")),
        ),
        _display_row(
            "Источник",
            source,
            note=f"Блок: {owner}",
            status=status,
        ),
    ]
    return {
        "title": "Коммерция",
        "subtitle": "Заказы и выкупы из core-safe cabinet_commerce.",
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


def build_funnel_section_v2(
    snapshot: dict[str, Any],
    cabinet_commerce: dict[str, Any],
    debug: dict[str, Any] | None,
) -> FunnelSectionV2:
    _ = debug
    cabinet = _safe_dict(cabinet_commerce)
    cabinet_available = bool(cabinet.get("available", False))
    cabinet_source = _safe_str(cabinet.get("source")) or "cabinet_commerce_daily"
    orders_count = _safe_int(cabinet.get("orders_count"))
    buyouts_count = _safe_int(cabinet.get("buyouts_count"))
    upper = _clean_core_upper_funnel(snapshot)

    rows: list[FunnelStageRowV2] = [
        _upper_funnel_stage_row("Показы", upper, ("views", "impressions", "shows")),
        _upper_funnel_stage_row("Клики", upper, ("clicks", "click_count")),
        _upper_funnel_stage_row("Корзина", upper, ("add_to_cart", "cart_count", "basket_count")),
        _funnel_row(
            "Заказы",
            _format_display_int(orders_count, "шт"),
            source=cabinet_source,
            status=_display_status(cabinet_available, orders_count),
            note="Нижняя часть воронки из cabinet_commerce.",
        ),
        _funnel_row(
            "Выкупы",
            _format_display_int(buyouts_count, "шт"),
            source=cabinet_source,
            status=_display_status(cabinet_available, buyouts_count),
            note="Нижняя часть воронки из cabinet_commerce.",
        ),
    ]

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

    lower_available = cabinet_available and (orders_count is not None or buyouts_count is not None)
    all_rows_available = all(row.get("status") == "ok" for row in rows)
    if all_rows_available:
        status = "ok"
        message = "Воронка собрана из clean core данных."
    elif lower_available:
        status = "partial"
        message = "Верхняя часть воронки недоступна в clean core snapshot; нули не подставлялись."
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


def _clean_core_ads_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    safe_snapshot = _safe_dict(snapshot)
    candidates = (
        safe_snapshot.get("ads_efficiency_daily"),
        safe_snapshot.get("advertising_daily"),
        safe_snapshot.get("ads_daily"),
        safe_snapshot.get("advertising_efficiency_daily"),
    )
    for candidate in candidates:
        block = _safe_dict(candidate)
        if not block:
            continue
        if "available" in block and not bool(block.get("available", False)):
            continue
        return block
    return {}


def _first_numeric(block: dict[str, Any], field_names: tuple[str, ...]) -> float | None:
    for field_name in field_names:
        if field_name in block:
            value = _safe_float(block.get(field_name))
            if value is not None:
                return value
    return None


def build_ads_section_v2(snapshot: dict[str, Any], debug: dict[str, Any] | None) -> AdsSectionV2:
    _ = debug
    ads = _clean_core_ads_block(snapshot)
    if not ads:
        rows = [
            _ads_row("Расход на рекламу", "нет данных", source="нет clean ads source", status="unavailable"),
            _ads_row("Заказы из рекламы", "нет данных", source="нет clean ads source", status="unavailable"),
            _ads_row("Выручка из рекламы", "нет данных", source="нет clean ads source", status="unavailable"),
            _ads_row("ДРР", "нет данных", source="нет clean ads source", status="unavailable"),
        ]
        return {
            "title": "Реклама",
            "subtitle": "Минимальный рекламный блок только из clean ads snapshot.",
            "rows": rows,
            "status": "unavailable",
            "message": "Данные по рекламе пока отсутствуют в core snapshot.",
        }

    source = _safe_str(ads.get("source")) or "wb_api_core_ads"
    ads_spend = _first_numeric(ads, ("ads_spend", "ad_spend", "spend", "advertising_spend", "cost"))
    ad_orders = _first_numeric(ads, ("ad_orders", "ads_orders", "orders_from_ads", "orders_count", "attributed_orders"))
    ad_revenue = _first_numeric(
        ads,
        ("revenue_from_ads", "ads_revenue", "ad_revenue", "revenue_total", "revenue", "attributed_revenue"),
    )

    drr: float | None = None
    if ads_spend is not None and ad_revenue is not None and ad_revenue > 0:
        drr = round(float(ads_spend) / float(ad_revenue) * 100.0, 2)

    rows = [
        _ads_row(
            "Расход на рекламу",
            _format_display_money(ads_spend),
            source=source,
            status=_display_status(True, ads_spend),
            note="Только из clean ads block.",
        ),
        _ads_row(
            "Заказы из рекламы",
            _format_display_int(ad_orders, "шт"),
            source=source,
            status=_display_status(True, ad_orders),
            note="Только из clean ads block.",
        ),
        _ads_row(
            "Выручка из рекламы",
            _format_display_money(ad_revenue),
            source=source,
            status=_display_status(True, ad_revenue),
            note="Только из clean ads block.",
        ),
        _ads_row(
            "ДРР",
            _format_display_percent(drr),
            source=source if drr is not None else "нет данных",
            status="ok" if drr is not None else "unavailable",
            note="Рассчитано в builder только из clean ads spend и revenue.",
        ),
    ]

    ok_count = sum(1 for row in rows if row.get("status") == "ok")
    if ok_count == len(rows):
        status = "ok"
        message = "Рекламные данные получены из clean ads block."
    elif ok_count > 0:
        status = "partial"
        message = "Рекламный блок есть, но часть значений отсутствует."
    else:
        status = "unavailable"
        message = "Clean ads block есть, но полезные значения отсутствуют."

    return {
        "title": "Реклама",
        "subtitle": "Минимальный рекламный блок только из clean ads snapshot.",
        "rows": rows,
        "status": status,
        "message": message,
    }


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


def build_report_payload_v2(snapshot: dict[str, Any], debug: dict[str, Any] | None = None) -> ReportPayloadV2:
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

    meta_block = {
        "contract_version": "report_payload_v2",
        "seller_id": seller_id,
        "report_date": report_date,
        "operational_date": operational_date,
        "snapshot_source_mode": snapshot_source_mode,
        "debug_available": debug is not None,
    }
    cabinet_block = {
        "available": bool(cabinet_daily.get("available", False)) and bool(cabinet_daily),
        "source": _safe_str(cabinet_daily.get("source")) or "missing",
        "owner_block": "cabinet_commerce_daily",
        "target_date": _safe_str(cabinet_daily.get("target_date")) or None,
        "orders_count": _safe_int(cabinet_daily.get("orders_count")),
        "orders_amount": _safe_float(cabinet_daily.get("orders_amount")),
        "buyouts_count": buyouts_count,
        "buyouts_amount": buyouts_amount,
    }
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
    live_block = {
        "status": live_status,
        "orders": _build_live_metric(live_orders),
        "sales": _build_live_metric(live_sales),
        "stocks": _build_live_metric(live_stocks),
    }

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
        "ads_section": build_ads_section_v2(snapshot, debug),
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
