"""Build unified audit facts for Ozon MVP (products + cogs)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo
from typing import Any

from audit.ozon_loader import (
    OZON_FILE_TYPES,
    build_cogs_match_index,
    match_cogs_for_sku,
    parse_ozon_cogs_file,
    parse_ozon_products_file,
    scan_ozon_input_files,
    select_best_ozon_files,
)


WB_TIMEZONE = ZoneInfo("Europe/Moscow")
REQUIRED_TYPES = ("ozon_products_report",)
OPTIONAL_TYPES = ("cogs",)


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _resolve_ozon_input_root(input_dir: str) -> str:
    from pathlib import Path

    p = Path(input_dir)
    if p.name.lower() == "ozon":
        return str(p)
    nested = p / "ozon"
    if nested.exists() and nested.is_dir():
        return str(nested)
    return str(p)


def _build_inputs_section(
    *,
    input_dir: str,
    detected_files: list[Any],
    selected_files: dict[str, Any],
    missing_required: list[str],
    missing_optional: list[str],
) -> dict[str, Any]:
    found_files = []
    for item in detected_files:
        found_files.append(
            {
                "path": item.path,
                "type": item.file_type,
                "score": item.score,
                "detected_by": item.detected_by,
                "sheets": item.sheets,
                "sample_columns": item.sample_columns,
            }
        )

    selected = {}
    for file_type in OZON_FILE_TYPES:
        item = selected_files.get(file_type)
        selected[file_type] = item.path if item else ""

    blocks_collected = [k for k, v in selected.items() if v]
    blocks_skipped = [k for k in OZON_FILE_TYPES if k not in blocks_collected]

    return {
        "input_dir": input_dir,
        "found_files": found_files,
        "selected_files": selected,
        "blocks_collected": blocks_collected,
        "blocks_skipped": blocks_skipped,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }


def _build_ozon_products_summary(items: list[dict[str, Any]], diagnostics: dict[str, Any]) -> dict[str, Any]:
    missing_columns = set(str(x) for x in (diagnostics.get("missing_columns") or []))
    parser_warnings = [str(x) for x in (diagnostics.get("warnings") or [])]

    total_orders = None if "orders" in missing_columns else sum(_to_int(x.get("orders")) for x in items)
    total_revenue = None if "revenue" in missing_columns else sum(_to_float(x.get("revenue")) for x in items)
    total_views = sum(_to_int(x.get("views")) for x in items)

    conv_values = [x.get("conversion") for x in items if x.get("conversion") is not None]
    avg_conversion = (sum(_to_float(x) for x in conv_values) / len(conv_values)) if conv_values else None

    return {
        "rows_count": len(items),
        "total_orders": (int(total_orders) if total_orders is not None else None),
        "total_revenue": (round(total_revenue, 2) if total_revenue is not None else None),
        "total_views": int(total_views),
        "avg_conversion": (round(float(avg_conversion), 4) if avg_conversion is not None else None),
        "metrics_warnings": parser_warnings,
        "diagnostics": diagnostics,
    }


def _build_sku_profit(items: list[dict[str, Any]], cogs_index: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stats = {"ok": 0, "no_cogs": 0, "no_orders": 0}

    for item in items:
        sku = _first_text(item.get("sku"), item.get("offer_id"), item.get("name")) or None
        offer_id = item.get("offer_id")
        name = item.get("name")
        orders_raw = item.get("orders")
        revenue_total = _to_float(item.get("revenue"))
        stock = _to_float(item.get("stock")) if item.get("stock") is not None else None
        buyouts = _to_int(item.get("buyouts")) if item.get("buyouts") is not None else None

        orders_count = _to_int(orders_raw) if orders_raw is not None else None
        cogs_unit, matched_by = match_cogs_for_sku(
            sku=sku,
            offer_id=offer_id,
            seller_code=offer_id,
            cogs_index=cogs_index,
        )

        cogs_total = None
        gross_profit = None
        if cogs_unit is None:
            status = "no_cogs"
        elif orders_count is None:
            status = "no_orders"
        else:
            cogs_total = float(orders_count) * float(cogs_unit)
            gross_profit = float(revenue_total) - float(cogs_total)
            status = "ok"

        stats[status] = stats.get(status, 0) + 1
        out.append(
            {
                "sku": sku,
                "offer_id": offer_id,
                "name": name,
                "orders": orders_count,
                "revenue_total": round(revenue_total, 2),
                "cogs_unit": (round(float(cogs_unit), 2) if cogs_unit is not None else None),
                "cogs_total": (round(float(cogs_total), 2) if cogs_total is not None else None),
                "gross_profit": (round(float(gross_profit), 2) if gross_profit is not None else None),
                "profit_status": status,
                "cogs_matched_by": matched_by,
                "views": (_to_int(item.get("views")) if item.get("views") is not None else None),
                "conversion": (_to_float(item.get("conversion")) if item.get("conversion") is not None else None),
                "price": (_to_float(item.get("price")) if item.get("price") is not None else None),
                "stock": stock,
                "buyouts": buyouts,
                "id_source": item.get("id_source"),
            }
        )

    out_sorted = sorted(
        out,
        key=lambda x: (
            float(x.get("gross_profit")) if x.get("gross_profit") is not None else float("-inf"),
            _to_float(x.get("revenue_total")),
            _to_int(x.get("orders")),
        ),
        reverse=True,
    )
    return out_sorted, stats


def _build_abc(items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [x for x in items if x.get("gross_profit") is not None]
    valid = sorted(valid, key=lambda x: float(x.get("gross_profit") or 0.0), reverse=True)

    if not valid:
        # Fallback: if profit cannot be computed (e.g. no COGS), build ABC by revenue.
        revenue_rows = [x for x in items if _to_float(x.get("revenue_total")) > 0]
        revenue_rows = sorted(revenue_rows, key=lambda x: float(x.get("revenue_total") or 0.0), reverse=True)
        if not revenue_rows:
            return {
                "items": [],
                "summary": {
                    "status": "no_gross_profit_data",
                    "basis": "gross_profit",
                    "basis_note": "Недостаточно данных для ABC-анализа.",
                    "a_count": 0,
                    "b_count": 0,
                    "c_count": 0,
                },
            }

        total_revenue = sum(_to_float(x.get("revenue_total")) for x in revenue_rows)
        cumulative = 0.0
        revenue_items_out = []
        for idx, item in enumerate(revenue_rows):
            revenue = max(_to_float(item.get("revenue_total")), 0.0)
            cumulative += revenue
            share = (cumulative / total_revenue) if total_revenue > 0 else 0.0
            if share <= 0.80 or idx == 0:
                abc = "A"
            elif share <= 0.95:
                abc = "B"
            else:
                abc = "C"
            revenue_items_out.append({**item, "abc_class": abc, "cum_revenue_share": round(share, 4)})

        return {
            "items": revenue_items_out,
            "summary": {
                "status": "fallback_revenue_no_cogs",
                "basis": "revenue",
                "basis_note": "ABC по выручке (fallback, т.к. нет COGS)",
                "total_items": len(revenue_items_out),
                "a_count": len([x for x in revenue_items_out if x.get("abc_class") == "A"]),
                "b_count": len([x for x in revenue_items_out if x.get("abc_class") == "B"]),
                "c_count": len([x for x in revenue_items_out if x.get("abc_class") == "C"]),
                "total_revenue": round(total_revenue, 2),
            },
        }

    total_positive_profit = sum(max(float(x.get("gross_profit") or 0.0), 0.0) for x in valid)
    items_out = []
    if total_positive_profit <= 0:
        n = len(valid)
        a_cut = max(int(round(n * 0.2)), 1)
        b_cut = max(int(round(n * 0.5)), a_cut)
        for idx, item in enumerate(valid):
            if idx < a_cut:
                abc = "A"
            elif idx < b_cut:
                abc = "B"
            else:
                abc = "C"
            items_out.append({**item, "abc_class": abc, "cum_profit_share": None})
    else:
        cum = 0.0
        for item in valid:
            gp = max(float(item.get("gross_profit") or 0.0), 0.0)
            cum += gp
            share = cum / total_positive_profit if total_positive_profit else 0.0
            if share <= 0.80:
                abc = "A"
            elif share <= 0.95:
                abc = "B"
            else:
                abc = "C"
            items_out.append({**item, "abc_class": abc, "cum_profit_share": round(share, 4)})

    summary = {
        "status": "ok",
        "basis": "gross_profit",
        "basis_note": "ABC по валовой прибыли.",
        "total_items": len(items_out),
        "a_count": len([x for x in items_out if x.get("abc_class") == "A"]),
        "b_count": len([x for x in items_out if x.get("abc_class") == "B"]),
        "c_count": len([x for x in items_out if x.get("abc_class") == "C"]),
        "total_positive_profit": round(total_positive_profit, 2),
    }
    return {"items": items_out, "summary": summary}


def _build_decision_layer(
    *,
    sku_profit_items: list[dict[str, Any]],
    abc_analysis: dict[str, Any],
    products_diagnostics: dict[str, Any],
    cogs_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    loss_analysis = []
    sku_problems = []
    growth_points = []
    data_gaps = []

    total_revenue = sum(_to_float(x.get("revenue_total")) for x in sku_profit_items)
    total_orders = sum(_to_int(x.get("orders")) for x in sku_profit_items if x.get("orders") is not None)
    known_profit_items = [x for x in sku_profit_items if x.get("gross_profit") is not None]
    gross_profit_total = sum(_to_float(x.get("gross_profit")) for x in known_profit_items)
    profit_state = "loss" if known_profit_items and gross_profit_total < 0 else "profit" if known_profit_items and gross_profit_total > 0 else "unknown"

    if profit_state == "loss":
        loss_analysis.append(
            {
                "type": "gross_profit_negative",
                "reason": "Суммарная валовая прибыль по SKU отрицательная",
                "numbers": {"gross_profit_total": round(gross_profit_total, 2)},
            }
        )

    for item in sku_profit_items:
        gp = item.get("gross_profit")
        status = item.get("profit_status")
        orders = item.get("orders")
        revenue = _to_float(item.get("revenue_total"))

        if status == "no_cogs":
            sku_problems.append(
                {
                    "type": "no_cogs",
                    "sku": item.get("sku"),
                    "offer_id": item.get("offer_id"),
                    "name": item.get("name"),
                    "reason": "Нет себестоимости, валовая прибыль не рассчитана",
                }
            )
            continue

        if gp is not None and _to_float(gp) < 0:
            sku_problems.append(
                {
                    "type": "loss_sku",
                    "sku": item.get("sku"),
                    "offer_id": item.get("offer_id"),
                    "name": item.get("name"),
                    "reason": "SKU убыточный по валовой прибыли",
                    "numbers": {"gross_profit": round(_to_float(gp), 2)},
                }
            )

        if orders is not None and _to_int(orders) <= 1:
            sku_problems.append(
                {
                    "type": "low_orders",
                    "sku": item.get("sku"),
                    "offer_id": item.get("offer_id"),
                    "name": item.get("name"),
                    "reason": "Недостаточная отдача: мало заказов",
                    "numbers": {"orders": _to_int(orders), "revenue_total": round(revenue, 2)},
                }
            )

        if _to_float(item.get("gross_profit")) > 0 or revenue >= 10000:
            growth_points.append(
                {
                    "type": "growth_candidate",
                    "sku": item.get("sku"),
                    "offer_id": item.get("offer_id"),
                    "name": item.get("name"),
                    "numbers": {
                        "gross_profit": item.get("gross_profit"),
                        "revenue_total": item.get("revenue_total"),
                        "orders": item.get("orders"),
                    },
                }
            )

    abc_basis = ((abc_analysis.get("summary") or {}).get("basis") or "gross_profit")
    for item in (abc_analysis.get("items") or []):
        if abc_basis == "gross_profit" and item.get("abc_class") == "C" and _to_float(item.get("gross_profit")) <= 0:
            sku_problems.append(
                {
                    "type": "candidate_disable_or_rework",
                    "sku": item.get("sku"),
                    "offer_id": item.get("offer_id"),
                    "name": item.get("name"),
                    "reason": "Кандидат на отключение/пересмотр: класс C и неположительная валовая прибыль",
                    "numbers": {"abc_class": "C", "gross_profit": item.get("gross_profit")},
                }
            )

    missing_columns = products_diagnostics.get("missing_columns") or []
    if missing_columns:
        data_gaps.append(
            {
                "type": "products_missing_columns",
                "details": missing_columns,
                "diagnostics": {
                    "missing_columns": missing_columns,
                    "source_columns": products_diagnostics.get("source_columns") or [],
                    "resolved_columns": products_diagnostics.get("resolved_columns") or {},
                    "unresolved_columns": products_diagnostics.get("unresolved_columns") or [],
                },
            }
        )

    if "revenue" in [str(x) for x in missing_columns]:
        data_gaps.append(
            {
                "type": "products_revenue_missing",
                "details": "revenue column missing caused empty revenue metrics",
            }
        )

    for warning in (products_diagnostics.get("warnings") or []):
        data_gaps.append({"type": "products_parser_warning", "details": str(warning)})

    if cogs_diagnostics.get("status") != "ok":
        data_gaps.append(
            {
                "type": "cogs_not_loaded",
                "details": cogs_diagnostics,
            }
        )
    data_gaps.append(
        {
            "type": "missing_reports_for_full_profit",
            "details": [
                "Нет фин. отчета Ozon (чистая прибыль кабинета не рассчитана)",
                "Нет рекламного отчета Ozon (реклама не проанализирована)",
                "Нет отчета по остаткам Ozon (stock-анализ ограничен)",
            ],
        }
    )

    return {
        "profit_state": profit_state,
        "kpi": {
            "revenue_total": round(total_revenue, 2),
            "orders_total": int(total_orders),
            "gross_profit_total_known": round(gross_profit_total, 2) if known_profit_items else None,
            "known_profit_items_count": len(known_profit_items),
        },
        "loss_analysis": loss_analysis,
        "sku_problems": sku_problems[:300],
        "ads_problems": [],
        "stock_problems": [],
        "growth_points": growth_points[:300],
        "data_gaps": data_gaps,
    }


def _build_actions(decision_layer: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    sku_problems = decision_layer.get("sku_problems") or []
    loss_items = [x for x in sku_problems if x.get("type") == "loss_sku"]
    no_cogs_items = [x for x in sku_problems if x.get("type") == "no_cogs"]
    low_orders_items = [x for x in sku_problems if x.get("type") == "low_orders"]
    growth = decision_layer.get("growth_points") or []

    if no_cogs_items:
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Добавить себестоимость для SKU без cogs и пересчитать валовую прибыль",
                "why": "Часть ассортимента не имеет расчета прибыли",
                "expected_effect": "Полный контроль прибыльности по SKU",
                "numbers": {"sku_without_cogs": len(no_cogs_items)},
            }
        )
    if loss_items:
        actions.append(
            {
                "priority": "P0",
                "area": "sku",
                "action": "Остановить продвижение убыточных SKU и пересмотреть цену/себестоимость",
                "why": "SKU дают отрицательную валовую прибыль",
                "expected_effect": "Снижение доли убыточных продаж",
                "numbers": {"loss_sku_count": len(loss_items)},
            }
        )
    if low_orders_items:
        actions.append(
            {
                "priority": "P1",
                "area": "sku",
                "action": "Переработать карточки SKU с низкими заказами: контент, цена, позиционирование",
                "why": "SKU не дают достаточной отдачи",
                "expected_effect": "Рост заказов по слабым позициям",
                "numbers": {"low_orders_sku_count": len(low_orders_items)},
            }
        )
    if growth:
        actions.append(
            {
                "priority": "P1",
                "area": "sku",
                "action": "Усилить ассортиментные лидеры с положительной валовой прибылью",
                "why": "Есть SKU с подтвержденным потенциалом роста",
                "expected_effect": "Рост выручки без ухудшения валовой прибыли",
                "numbers": {"growth_candidates": len(growth)},
            }
        )
    if not actions:
        actions.append(
            {
                "priority": "P2",
                "area": "finance",
                "action": "Запросить недостающие отчеты Ozon для расширенного аудита",
                "why": "Недостаточно данных для глубоких действий",
                "expected_effect": "Переход к полному аудиту кабинета",
                "numbers": {},
            }
        )
    return actions


def build_ozon_audit_facts(input_dir: str = "audit/input/ozon", period_label: str = "") -> dict[str, Any]:
    root_input_dir = _resolve_ozon_input_root(input_dir)
    detected_files = scan_ozon_input_files(root_input_dir)
    selected_files = select_best_ozon_files(detected_files)

    missing_required = [k for k in REQUIRED_TYPES if k not in selected_files]
    missing_optional = [k for k in OPTIONAL_TYPES if k not in selected_files]

    products_rows: list[dict[str, Any]] = []
    products_diagnostics: dict[str, Any] = {"status": "missing_file"}
    cogs_map: dict[str, float] = {}
    cogs_diagnostics: dict[str, Any] = {"status": "missing_file"}

    if "ozon_products_report" in selected_files:
        products_rows, products_diagnostics = parse_ozon_products_file(selected_files["ozon_products_report"].path)
    if "cogs" in selected_files:
        cogs_map, cogs_diagnostics = parse_ozon_cogs_file(selected_files["cogs"].path)

    cogs_index = build_cogs_match_index(cogs_map)
    sku_profit_items, sku_profit_stats = _build_sku_profit(products_rows, cogs_index)
    abc_analysis = _build_abc(sku_profit_items)
    ozon_products_summary = _build_ozon_products_summary(products_rows, products_diagnostics)

    top_sku_by_revenue = sorted(
        [x for x in sku_profit_items if _to_float(x.get("revenue_total")) > 0],
        key=lambda x: (_to_float(x.get("revenue_total")), _to_int(x.get("orders"))),
        reverse=True,
    )[:10]
    top_sku_by_orders = sorted(
        [x for x in sku_profit_items if _to_int(x.get("orders")) > 0],
        key=lambda x: (_to_int(x.get("orders")), _to_float(x.get("revenue_total"))),
        reverse=True,
    )[:10]
    sku_without_orders = [x for x in sku_profit_items if _to_int(x.get("orders")) <= 0][:100]
    sku_with_stock = sorted(
        [x for x in sku_profit_items if _to_float(x.get("stock")) > 0],
        key=lambda x: (_to_float(x.get("stock")), _to_float(x.get("revenue_total"))),
        reverse=True,
    )[:100]

    gross_revenue = sum(_to_float(x.get("revenue_total")) for x in sku_profit_items)
    known_profit_items = [x for x in sku_profit_items if x.get("gross_profit") is not None]
    gross_profit_known = sum(_to_float(x.get("gross_profit")) for x in known_profit_items)
    margin_known = (gross_profit_known / gross_revenue) if gross_revenue > 0 and known_profit_items else None

    financial_summary = {
        "status": "partial_no_ozon_financial_report",
        "gross_revenue_from_products": round(gross_revenue, 2),
        "gross_profit_from_products_with_cogs": round(gross_profit_known, 2) if known_profit_items else None,
        "margin_from_products_with_cogs": (round(float(margin_known), 4) if margin_known is not None else None),
        "note": "Чистая прибыль кабинета не рассчитана: отсутствует фин. отчет Ozon.",
    }
    ads_summary = {
        "status": "missing",
        "note": "Реклама не проанализирована: отсутствует рекламный отчет Ozon.",
    }
    stock_summary = {
        "status": "missing",
        "note": "Остатки не проанализированы: отсутствует отчет по остаткам Ozon.",
    }

    decision_layer = _build_decision_layer(
        sku_profit_items=sku_profit_items,
        abc_analysis=abc_analysis,
        products_diagnostics=products_diagnostics,
        cogs_diagnostics=cogs_diagnostics,
    )
    actions = _build_actions(decision_layer)

    inputs = _build_inputs_section(
        input_dir=root_input_dir,
        detected_files=detected_files,
        selected_files=selected_files,
        missing_required=missing_required,
        missing_optional=missing_optional,
    )

    missing_blocks = []
    if "cogs" not in selected_files:
        missing_blocks.append("cogs")
    missing_blocks.extend(["financial_report_ozon", "ads_report_ozon", "stocks_report_ozon"])

    report_date = dt.datetime.now(WB_TIMEZONE).date().isoformat()

    return {
        "date": report_date,
        "report_type": "audit",
        "source": "ozon",
        "period": {"label": period_label or report_date},
        "inputs": inputs,
        "ozon_products_summary": ozon_products_summary,
        "sku_profit": {
            "items": sku_profit_items,
            "summary": {
                "total_items": len(sku_profit_items),
                "ok_items": sku_profit_stats.get("ok", 0),
                "no_cogs_items": sku_profit_stats.get("no_cogs", 0),
                "no_orders_items": sku_profit_stats.get("no_orders", 0),
                "sku_without_orders_count": len(sku_without_orders),
                "sku_with_stock_count": len(sku_with_stock),
            },
        },
        "stock_summary": stock_summary,
        "financial_summary": financial_summary,
        "ads_summary": ads_summary,
        "abc_analysis": abc_analysis,
        "top_sku_by_revenue": top_sku_by_revenue,
        "top_sku_by_orders": top_sku_by_orders,
        "sku_without_orders": sku_without_orders,
        "sku_with_stock": sku_with_stock,
        "decision_layer": decision_layer,
        "actions": actions,
        "missing_blocks": missing_blocks,
        "funnel_summary": {},
        "search_insights": {},
        "notes": [
            "Ozon MVP аудит построен по отчету товаров и файлу себестоимости.",
            "Чистая прибыль кабинета требует фин. отчета Ozon.",
            "Анализ рекламы требует рекламного отчета Ozon.",
        ],
    }
