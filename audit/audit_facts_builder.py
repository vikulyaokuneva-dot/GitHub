"""Build unified offline audit facts from audit/input files."""

from __future__ import annotations

import datetime as dt
import os
from collections import defaultdict
from zoneinfo import ZoneInfo
from typing import Any

from audit.audit_loader import (
    FILE_TYPES,
    parse_ads_file,
    parse_cogs_file,
    parse_finance_file,
    parse_funnel_file,
    parse_search_file,
    parse_stocks_file,
    scan_input_files,
    select_best_detected_files,
)
from src.metrics import calc_ads_metrics, calc_financial_metrics, calc_funnel_metrics
from src.sku_performance_analyzer import analyze_sku_performance


WB_TIMEZONE = ZoneInfo(os.getenv("WB_TIMEZONE", "Europe/Moscow"))
REQUIRED_TYPES = ("finance", "funnel", "stocks")
OPTIONAL_TYPES = ("ads", "search", "cogs")


def _iso(d: dt.date) -> str:
    return d.isoformat()


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


def _audit_stock_summary(stocks_raw: list[dict[str, Any]], avg_daily_sales: float, lead_days: int = 14, safety_days: int = 7) -> dict[str, Any]:
    total_units = 0
    keys = set()
    by_key: dict[str, int] = defaultdict(int)

    for r in (stocks_raw or []):
        if not isinstance(r, dict):
            continue
        q = _to_int(r.get("quantityFull") or r.get("quantity") or r.get("qty") or r.get("stock"))
        if q <= 0:
            continue
        total_units += q
        key = r.get("nmId") or r.get("nm_id") or r.get("supplierArticle") or r.get("vendorCode")
        if key:
            skey = str(key)
            keys.add(skey)
            by_key[skey] += q

    days_of_cover = (float(total_units) / float(avg_daily_sales)) if avg_daily_sales else 0.0
    threshold = int(lead_days + safety_days)

    return {
        "stock_units": int(total_units),
        "sku_count": int(len(keys)),
        "days_of_cover": round(float(days_of_cover or 0.0), 2),
        "risk_of_oos": bool(days_of_cover != 0 and days_of_cover < threshold),
        "threshold_days": threshold,
        "items_count": int(len(stocks_raw or [])),
        "by_sku_or_article": by_key,
        "note": (
            "Остатки собраны из выгрузки файлов audit/input. "
            "Если в файле нет Артикул WB, SKU-level анализ строится по артикулу продавца."
        ),
    }


def _build_search_insights(search_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not search_rows:
        return {
            "status": "missing",
            "message": "search file not provided",
            "profitable": [],
            "unprofitable": [],
            "potential": [],
        }

    profitable: list[dict[str, Any]] = []
    unprofitable: list[dict[str, Any]] = []
    potential: list[dict[str, Any]] = []

    for row in search_rows:
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        impressions = _to_int(row.get("impressions"))
        clicks = _to_int(row.get("clicks"))
        orders = _to_int(row.get("orders"))
        buyouts = _to_int(row.get("buyouts"))
        spend = _to_float(row.get("spend"))
        revenue = _to_float(row.get("revenue"))

        payload = {
            "query": query,
            "impressions": impressions,
            "clicks": clicks,
            "orders": orders,
            "buyouts": buyouts,
            "spend": round(spend, 2),
            "revenue": round(revenue, 2),
            "roas": round((revenue / spend), 3) if spend > 0 else None,
        }

        if spend > 0 and (orders == 0 or revenue <= 0):
            unprofitable.append(payload)
        elif orders > 0 and (revenue > spend or spend == 0):
            profitable.append(payload)
        elif impressions > 0 and clicks == 0:
            potential.append(payload)

    return {
        "status": "ok",
        "profitable": profitable[:50],
        "unprofitable": unprofitable[:50],
        "potential": potential[:50],
        "summary": {
            "rows_count": len(search_rows),
            "profitable_count": len(profitable),
            "unprofitable_count": len(unprofitable),
            "potential_count": len(potential),
        },
    }


def _build_decision_layer(
    *,
    finance: dict[str, Any],
    funnel: dict[str, Any],
    ads: dict[str, Any],
    stock: dict[str, Any],
    sku_rows: list[dict[str, Any]],
    search_insights: dict[str, Any],
    missing_required: list[str],
    missing_optional: list[str],
) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    growth_points: list[dict[str, Any]] = []

    profit = _to_float(finance.get("profit"))
    revenue = _to_float(finance.get("gross_revenue"))
    margin = _to_float(finance.get("margin"))
    ads_spend = _to_float(ads.get("spend"))
    ads_revenue = _to_float(ads.get("revenue_attr"))
    roas = _to_float(ads.get("roas"))
    buyout_rate = _to_float(funnel.get("buyout_rate"))

    expense_components = [
        ("commission", _to_float(finance.get("commission"))),
        ("logistics", _to_float(finance.get("logistics"))),
        ("storage", _to_float(finance.get("storage"))),
        ("penalties", _to_float(finance.get("penalties"))),
        ("tax", _to_float(finance.get("tax"))),
        ("cogs_total", _to_float(finance.get("cogs_total"))),
    ]
    for name, value in sorted(expense_components, key=lambda x: x[1], reverse=True)[:3]:
        if value > 0:
            reasons.append(
                {
                    "category": "finance",
                    "reason": f"Высокий расход: {name}",
                    "numbers": {"amount": round(value, 2)},
                }
            )

    if ads_spend > 0 and ads_revenue <= 0:
        reasons.append(
            {
                "category": "ads",
                "reason": "Реклама убыточная: расход есть, атрибутированной выручки нет",
                "numbers": {"spend": round(ads_spend, 2), "revenue_attr": round(ads_revenue, 2)},
            }
        )
    elif ads_spend > 0 and roas < 1:
        reasons.append(
            {
                "category": "ads",
                "reason": "Реклама убыточная: ROAS ниже 1",
                "numbers": {"spend": round(ads_spend, 2), "roas": round(roas, 3)},
            }
        )

    if buyout_rate and buyout_rate < 0.6:
        reasons.append(
            {
                "category": "funnel",
                "reason": "Низкий % выкупа после заказа",
                "numbers": {"buyout_rate": round(buyout_rate, 4)},
            }
        )

    negative_margin_sku = finance.get("negative_margin_sku") or []
    unprofitable_sku = [
        {
            "sku": int(x.get("sku") or 0),
            "profit": round(_to_float(x.get("profit")), 2),
            "margin": round(_to_float(x.get("margin")), 4),
        }
        for x in negative_margin_sku[:50]
        if int(x.get("sku") or 0) > 0
    ]

    sku_without_sales = []
    dead_stock = []
    for row in sku_rows:
        sku = int(row.get("sku") or 0)
        stock_qty = _to_int(row.get("stock_qty"))
        buyouts = _to_int(row.get("buyouts"))
        if stock_qty > 0 and buyouts == 0:
            payload = {
                "sku": sku,
                "stock_qty": stock_qty,
                "orders": _to_int(row.get("orders")),
                "buyouts": buyouts,
                "revenue": round(_to_float(row.get("revenue")), 2),
            }
            sku_without_sales.append(payload)
            dead_stock.append(payload)

    ads_leaks = []
    if ads_spend > 0 and ads_revenue <= 0:
        ads_leaks.append(
            {
                "level": "cabinet",
                "spend": round(ads_spend, 2),
                "revenue_attr": round(ads_revenue, 2),
                "roas": round(roas, 3),
            }
        )

    for row in (search_insights.get("unprofitable") or [])[:50]:
        ads_leaks.append(
            {
                "level": "query",
                "query": row.get("query"),
                "spend": round(_to_float(row.get("spend")), 2),
                "orders": _to_int(row.get("orders")),
                "revenue": round(_to_float(row.get("revenue")), 2),
            }
        )

    top_profit = finance.get("top_sku_by_profit") or []
    for item in top_profit[:20]:
        growth_points.append(
            {
                "type": "sku_profit_leader",
                "sku": int(item.get("sku") or 0),
                "profit": round(_to_float(item.get("profit")), 2),
                "margin": round(_to_float(item.get("margin")), 4),
            }
        )
    for row in (search_insights.get("profitable") or [])[:20]:
        growth_points.append(
            {
                "type": "search_query",
                "query": row.get("query"),
                "orders": _to_int(row.get("orders")),
                "roas": row.get("roas"),
            }
        )

    status = "ok"
    if missing_required:
        status = "partial_required_missing"
    elif missing_optional:
        status = "partial_optional_missing"

    return {
        "status": status,
        "profit_state": "loss" if profit < 0 else "profit" if profit > 0 else "breakeven",
        "kpi": {
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "margin": round(margin, 4),
            "roas": round(roas, 3) if ads_spend > 0 else None,
        },
        "reasons_of_loss": reasons[:10],
        "unprofitable_sku": unprofitable_sku,
        "sku_without_sales": sku_without_sales[:100],
        "ads_leaks": ads_leaks[:100],
        "dead_stock": dead_stock[:100],
        "growth_points": growth_points[:100],
        "missing_data": {
            "required": missing_required,
            "optional": missing_optional,
        },
    }


def _build_actions(decision_layer: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    profit_state = decision_layer.get("profit_state")
    kpi = decision_layer.get("kpi") or {}

    if profit_state == "loss":
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Снизить крупнейшие расходные статьи до выхода в положительную маржу",
                "why": "Кабинет в убытке по финрезультату",
                "expected_effect": "Сокращение операционного убытка",
                "numbers": {
                    "profit": kpi.get("profit"),
                    "margin": kpi.get("margin"),
                },
            }
        )

    if decision_layer.get("ads_leaks"):
        actions.append(
            {
                "priority": "P0",
                "area": "ads",
                "action": "Отключить кампании и запросы с расходом без заказов",
                "why": "Реклама убыточная и сливает бюджет",
                "expected_effect": "Снижение рекламного расхода без потери выручки",
                "numbers": {
                    "leaks_count": len(decision_layer.get("ads_leaks") or []),
                },
            }
        )

    if decision_layer.get("unprofitable_sku"):
        actions.append(
            {
                "priority": "P1",
                "area": "sku",
                "action": "Убрать из продвижения SKU с отрицательной маржей и пересчитать цену/себестоимость",
                "why": "SKU тянут кабинет в минус",
                "expected_effect": "Рост валовой маржи по ассортименту",
                "numbers": {
                    "unprofitable_sku_count": len(decision_layer.get("unprofitable_sku") or []),
                },
            }
        )

    if decision_layer.get("dead_stock"):
        actions.append(
            {
                "priority": "P1",
                "area": "stock",
                "action": "Сократить мертвые остатки: распродать или убрать закупку по SKU без продаж",
                "why": "Деньги заморожены в остатках без движения",
                "expected_effect": "Высвобождение оборотного капитала",
                "numbers": {
                    "dead_stock_count": len(decision_layer.get("dead_stock") or []),
                },
            }
        )

    if not actions:
        actions.append(
            {
                "priority": "P2",
                "area": "finance",
                "action": "Зафиксировать текущую модель и масштабировать точки роста без увеличения убыточных расходов",
                "why": "Критичных отклонений не обнаружено",
                "expected_effect": "Контролируемый рост прибыли",
                "numbers": {
                    "profit": kpi.get("profit"),
                    "margin": kpi.get("margin"),
                },
            }
        )
    return actions


def _build_inputs_section(
    input_dir: str,
    detected_files: list[Any],
    selected_files: dict[str, Any],
    missing_required: list[str],
    missing_optional: list[str],
) -> dict[str, Any]:
    found = []
    for item in detected_files:
        found.append(
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
    for file_type in FILE_TYPES:
        item = selected_files.get(file_type)
        selected[file_type] = item.path if item else ""

    blocks_collected = [k for k, v in selected.items() if v]
    blocks_skipped = [k for k in FILE_TYPES if k not in blocks_collected]

    return {
        "input_dir": input_dir,
        "found_files": found,
        "selected_files": selected,
        "blocks_collected": blocks_collected,
        "blocks_skipped": blocks_skipped,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }


def build_audit_facts(input_dir: str = "audit/input", period_label: str = "") -> dict[str, Any]:
    tax_rate = float(os.getenv("WB_TAX_RATE", "0.06"))
    report_date = dt.datetime.now(WB_TIMEZONE).date()

    detected_files = scan_input_files(input_dir)
    selected_files = select_best_detected_files(detected_files)

    missing_required = [file_type for file_type in REQUIRED_TYPES if file_type not in selected_files]
    missing_optional = [file_type for file_type in OPTIONAL_TYPES if file_type not in selected_files]

    finance_rows = parse_finance_file(selected_files["finance"].path) if "finance" in selected_files else []
    funnel_rows = parse_funnel_file(selected_files["funnel"].path) if "funnel" in selected_files else []
    stocks_rows = parse_stocks_file(selected_files["stocks"].path) if "stocks" in selected_files else []
    ads_rows = parse_ads_file(selected_files["ads"].path) if "ads" in selected_files else []
    search_rows = parse_search_file(selected_files["search"].path) if "search" in selected_files else []
    cogs_rows = parse_cogs_file(selected_files["cogs"].path) if "cogs" in selected_files else []

    funnel_summary = calc_funnel_metrics(funnel_rows) if funnel_rows else {}
    financial_summary = calc_financial_metrics(finance_rows, tax_rate=tax_rate) if finance_rows else {"rows_count": 0}
    ads_summary = calc_ads_metrics(ads_rows) if ads_rows else {}

    period_days = 7
    if period_label and "_" in period_label:
        try:
            d1s, d2s = period_label.split("_", 1)
            d1 = dt.date.fromisoformat(d1s)
            d2 = dt.date.fromisoformat(d2s)
            period_days = max((d2 - d1).days + 1, 1)
        except Exception:
            period_days = 7

    avg_daily_sales = _to_float((funnel_summary or {}).get("buys")) / float(period_days or 1)
    stock_summary = _audit_stock_summary(stocks_rows, avg_daily_sales=avg_daily_sales)
    search_insights = _build_search_insights(search_rows)

    finance_status = "ok" if _to_int(financial_summary.get("rows_count")) > 0 else "missing"
    try:
        sku_performance = analyze_sku_performance(
            finance_summary=financial_summary,
            funnel_raw=funnel_rows,
            stocks_raw=stocks_rows,
            ads_raw=ads_rows,
            period_days=period_days,
            finance_status=finance_status,
        )
    except Exception as exc:
        sku_performance = {"error": f"sku_performance_failed: {exc}", "rows": [], "abc_summary": {}}

    sku_rows = (sku_performance.get("rows") or []) if isinstance(sku_performance, dict) else []
    sku_profit = sorted(
        [
            {
                "sku": _to_int(row.get("sku")),
                "revenue": round(_to_float(row.get("revenue")), 2),
                "profit": round(_to_float(row.get("profit")), 2),
                "margin": round(_to_float(row.get("margin")), 4),
                "stock_qty": _to_int(row.get("stock_qty")),
                "buyouts": _to_int(row.get("buyouts")),
            }
            for row in sku_rows
        ],
        key=lambda x: x["profit"],
        reverse=True,
    )

    decision_layer = _build_decision_layer(
        finance=financial_summary,
        funnel=funnel_summary,
        ads=ads_summary,
        stock=stock_summary,
        sku_rows=sku_rows,
        search_insights=search_insights,
        missing_required=missing_required,
        missing_optional=missing_optional,
    )
    actions = _build_actions(decision_layer)

    inputs = _build_inputs_section(
        input_dir=input_dir,
        detected_files=detected_files,
        selected_files=selected_files,
        missing_required=missing_required,
        missing_optional=missing_optional,
    )

    return {
        "date": _iso(report_date),
        "report_type": "audit",
        "timezone": str(WB_TIMEZONE),
        "tax_rate": tax_rate,
        "period": {
            "label": period_label or _iso(report_date),
            "days": int(period_days),
        },
        "inputs": inputs,
        "financial_summary": financial_summary,
        "funnel_summary": funnel_summary,
        "ads_summary": ads_summary,
        "stock_summary": stock_summary,
        "search_insights": search_insights,
        "cogs_input": {
            "rows_count": len(cogs_rows),
            "rows": cogs_rows[:200],
        },
        "sku_profit": sku_profit,
        "abc_analysis": (sku_performance.get("abc_summary") if isinstance(sku_performance, dict) else {}) or {},
        "decision_layer": decision_layer,
        "actions": actions,
        "notes": [
            "Аудит собран из файлов в audit/input без WB API.",
            "При отсутствии части файлов аудит строится по доступным данным и помечается как partial.",
            "Обязательные блоки: finance, funnel, stocks. Опциональные: ads, search, cogs.",
        ],
    }

