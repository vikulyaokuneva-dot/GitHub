"""Build unified offline WB audit facts from audit/input files."""

from __future__ import annotations

import datetime as dt
import os
import re
from math import ceil
from collections import defaultdict
from zoneinfo import ZoneInfo
from typing import Any

from audit.audit_loader import (
    FILE_TYPES,
    group_detected_files,
    parse_ads_file_with_diagnostics,
    parse_cogs_file,
    parse_finance_file_with_diagnostics,
    parse_funnel_file,
    parse_search_file_with_diagnostics,
    parse_stocks_file_with_diagnostics,
    scan_input_files,
)
from audit.logistics_model import SUPPLY_TYPE_BOX, compute_wb_logistics_estimate
from shared.logistics_reference import (
    HIGH_COEFFICIENT_ALERT,
    build_region_logistics_summary,
    flatten_warehouse_logistics_reference,
    load_warehouse_logistics_reference,
)
from src.metrics import calc_ads_metrics, calc_financial_metrics, calc_funnel_metrics
from src.sku_performance_analyzer import analyze_sku_performance


WB_TIMEZONE = ZoneInfo(os.getenv("WB_TIMEZONE", "Europe/Moscow"))
REQUIRED_TYPES = ("finance", "funnel", "stocks")
OPTIONAL_TYPES = ("ads", "search", "cogs")
LOCAL_MOVE_MIN_BATCH = int(os.getenv("WB_LOCAL_MOVE_MIN_BATCH", "5"))


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _date_ru(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def _parse_date_ymd(text: str) -> list[dt.date]:
    out: list[dt.date] = []
    if not text:
        return out
    for m in re.finditer(r"(?<!\d)(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", text):
        try:
            out.append(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except Exception:
            continue
    return out


def _parse_date_dmy(text: str) -> list[dt.date]:
    out: list[dt.date] = []
    if not text:
        return out
    for m in re.finditer(r"(?<!\d)(\d{1,2})[.](\d{1,2})[.](20\d{2})(?!\d)", text):
        try:
            out.append(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except Exception:
            continue
    return out


def _extract_dates_from_text(text: str) -> list[dt.date]:
    if not text:
        return []
    return _parse_date_ymd(text) + _parse_date_dmy(text)


def _derive_audit_period(
    *,
    period_label: str,
    report_date: dt.date,
    selected_files: dict[str, list[str]],
    parse_diagnostics: dict[str, Any],
    period_days: int,
) -> dict[str, str]:
    candidates: list[dt.date] = []

    if period_label:
        candidates.extend(_extract_dates_from_text(period_label))

    for files in selected_files.values():
        if not isinstance(files, list):
            continue
        for path in files:
            txt = str(path or "")
            candidates.extend(_extract_dates_from_text(txt))

    for value in parse_diagnostics.values():
        if isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, str):
                    candidates.extend(_extract_dates_from_text(inner))

    if candidates:
        date_from = min(candidates)
        date_to = max(candidates)
    else:
        days = max(int(period_days or 1), 1)
        date_to = report_date
        date_from = report_date - dt.timedelta(days=days - 1)

    if date_from > date_to:
        date_from, date_to = date_to, date_from

    return {
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "label_ru": f"\u0441 {_date_ru(date_from)} \u043f\u043e {_date_ru(date_to)}",
    }


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _norm_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip().lower()
    return " ".join(text.split())


def _to_float_relaxed(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(" ", "").replace(",", ".")
            if cleaned == "":
                return None
            return float(cleaned)
        return float(value)
    except Exception:
        return None


def _extract_first_numeric_from_rows(
    rows: list[dict[str, Any]] | None,
    *,
    key_hints: tuple[str, ...],
    positive_only: bool = True,
) -> float | None:
    if not rows:
        return None
    normalized_hints = tuple(_norm_text(x) for x in key_hints if _norm_text(x))
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, raw_value in row.items():
            key_norm = _norm_text(key)
            if not key_norm:
                continue
            if not any(hint in key_norm for hint in normalized_hints):
                continue
            value = _to_float_relaxed(raw_value)
            if value is None:
                continue
            if positive_only and value <= 0:
                continue
            return float(value)
    return None


def _estimate_item_price(
    *,
    funnel_summary: dict[str, Any],
    financial_summary: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float | None:
    orders = _to_int((funnel_summary or {}).get("orders"))
    revenue_orders = _to_float_or_none((funnel_summary or {}).get("revenue_orders"))
    if orders > 0 and revenue_orders is not None and revenue_orders > 0:
        return round(float(revenue_orders) / float(orders), 2)

    buys = _to_int((funnel_summary or {}).get("buys"))
    revenue_buyouts = _to_float_or_none((funnel_summary or {}).get("revenue_buyouts"))
    if buys > 0 and revenue_buyouts is not None and revenue_buyouts > 0:
        return round(float(revenue_buyouts) / float(buys), 2)

    sales_qty = _to_int((financial_summary or {}).get("sales_qty"))
    gross_revenue = _to_float_or_none((financial_summary or {}).get("gross_revenue"))
    if sales_qty > 0 and gross_revenue is not None and gross_revenue > 0:
        return round(float(gross_revenue) / float(sales_qty), 2)

    row_value = _extract_first_numeric_from_rows(
        funnel_rows,
        key_hints=(
            "price",
            "item_price",
            "retail_price",
            "цена",
            "средняя цена",
        ),
        positive_only=True,
    )
    if row_value is not None:
        return round(float(row_value), 2)

    row_value = _extract_first_numeric_from_rows(
        finance_rows,
        key_hints=(
            "retail_price_withdisc_rub",
            "retail_price",
            "цена",
            "price",
        ),
        positive_only=True,
    )
    if row_value is not None:
        return round(float(row_value), 2)
    return None


def _estimate_volume_liters(
    *,
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float | None:
    key_hints = (
        "volume_liters",
        "volume_liter",
        "volume_l",
        "volume",
        "литраж",
        "литр",
        "объем",
        "объём",
    )
    for rows in (funnel_rows, stocks_rows, finance_rows):
        value = _extract_first_numeric_from_rows(rows, key_hints=key_hints, positive_only=True)
        if value is not None:
            return round(float(value), 4)
    return None


def _estimate_localization_share_pct(
    *,
    local_orders_insights: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float | None:
    by_region = local_orders_insights.get("by_region")
    if isinstance(by_region, list):
        local_total = 0
        non_local_total = 0
        for row in by_region:
            if not isinstance(row, dict):
                continue
            local_total += _to_int(row.get("local_orders") or row.get("orders_local"))
            non_local_total += _to_int(row.get("non_local_orders") or row.get("orders_non_local"))
        denom = local_total + non_local_total
        if denom > 0:
            return round((float(local_total) / float(denom)) * 100.0, 2)

    key_hints = (
        "localization_share_pct",
        "localization_share",
        "local_share_pct",
        "доля локализации",
        "локализация",
    )
    for rows in (funnel_rows, stocks_rows, finance_rows):
        value = _extract_first_numeric_from_rows(rows, key_hints=key_hints, positive_only=False)
        if value is None:
            continue
        bounded = min(max(float(value), 0.0), 100.0)
        return round(bounded, 2)
    return None


def _estimate_warehouse_coef(
    *,
    local_orders_insights: dict[str, Any],
    logistics_payload: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> float:
    weighted_sum = 0.0
    weighted_orders = 0
    signals = logistics_payload.get("locality_signals")
    if isinstance(signals, list):
        for item in signals:
            if not isinstance(item, dict):
                continue
            avg_coef = _to_float_or_none(item.get("avg_coefficient"))
            orders = _to_int(item.get("orders"))
            if avg_coef is None or orders <= 0:
                continue
            weighted_sum += float(avg_coef) * float(orders)
            weighted_orders += orders
    if weighted_orders > 0:
        return round(weighted_sum / float(weighted_orders), 2)

    by_region = local_orders_insights.get("by_region")
    if isinstance(by_region, list):
        values: list[float] = []
        for row in by_region:
            if not isinstance(row, dict):
                continue
            coef = _to_float_or_none(row.get("logistics_avg_coefficient"))
            if coef is not None and coef > 0:
                values.append(float(coef))
        if values:
            return round(sum(values) / float(len(values)), 2)

    key_hints = (
        "warehouse_coef",
        "warehouse_coefficient",
        "коэффициент склада",
        "коэф склада",
        "коэффициент логистики",
        "logistics_coefficient",
    )
    for rows in (funnel_rows, stocks_rows, finance_rows):
        value = _extract_first_numeric_from_rows(rows, key_hints=key_hints, positive_only=True)
        if value is not None:
            return float(value)
    return 1.0


def _build_logistics_formula_model_payload(
    *,
    funnel_summary: dict[str, Any],
    financial_summary: dict[str, Any],
    local_orders_insights: dict[str, Any],
    logistics_payload: dict[str, Any],
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
    finance_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    volume_liters = _estimate_volume_liters(
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
        finance_rows=finance_rows,
    )
    item_price = _estimate_item_price(
        funnel_summary=funnel_summary,
        financial_summary=financial_summary,
        funnel_rows=funnel_rows,
        finance_rows=finance_rows,
    )
    localization_share_pct = _estimate_localization_share_pct(
        local_orders_insights=local_orders_insights,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
        finance_rows=finance_rows,
    )
    warehouse_coef = _estimate_warehouse_coef(
        local_orders_insights=local_orders_insights,
        logistics_payload=logistics_payload,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
        finance_rows=finance_rows,
    )
    estimate = compute_wb_logistics_estimate(
        volume_liters=volume_liters,
        item_price=item_price,
        warehouse_coef=warehouse_coef,
        localization_share_pct=localization_share_pct,
        supply_type=SUPPLY_TYPE_BOX,
        is_sgt=False,
        is_courier_wb=False,
    )
    estimate["source"] = "wb_formula_model_v1"
    estimate["model_version"] = "2026-04-05"
    estimate["input_candidates"] = {
        "volume_liters": volume_liters,
        "item_price": item_price,
        "warehouse_coef": warehouse_coef,
        "localization_share_pct": localization_share_pct,
    }
    return estimate


def _geo_label(row: dict[str, Any]) -> str:
    for key in ("region", "city", "warehouse", "cluster", "federal_district"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_local_orders_insights(
    *,
    funnel_rows: list[dict[str, Any]],
    stocks_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    orders_by_sku_region: dict[tuple[int, str], int] = defaultdict(int)
    total_orders_by_sku: dict[int, int] = defaultdict(int)
    total_orders_by_region: dict[str, int] = defaultdict(int)
    stock_by_sku_region: dict[tuple[int, str], int] = defaultdict(int)
    stock_by_region: dict[str, int] = defaultdict(int)

    orders_rows_scanned = 0
    orders_rows_with_geo = 0
    for row in funnel_rows or []:
        if not isinstance(row, dict):
            continue
        orders_rows_scanned += 1
        sku = _to_int(row.get("nmId") or row.get("nm_id") or row.get("sku"))
        orders = _to_int(row.get("orderCount") or row.get("orders") or row.get("quantity"))
        geo = _geo_label(row)
        if sku <= 0 or orders <= 0:
            continue
        if not geo:
            continue
        orders_rows_with_geo += 1
        orders_by_sku_region[(sku, geo)] += orders
        total_orders_by_sku[sku] += orders
        total_orders_by_region[geo] += orders

    stock_rows_scanned = 0
    stock_rows_with_geo = 0
    for row in stocks_rows or []:
        if not isinstance(row, dict):
            continue
        stock_rows_scanned += 1
        sku = _to_int(row.get("nmId") or row.get("nm_id") or row.get("sku"))
        geo = _geo_label(row)
        qty = _to_int(row.get("quantityFull") or row.get("quantity") or row.get("qty") or row.get("stock"))
        if sku <= 0 or not geo:
            continue
        stock_rows_with_geo += 1
        qty = max(qty, 0)
        stock_by_sku_region[(sku, geo)] += qty
        stock_by_region[geo] += qty

    total_orders = sum(total_orders_by_region.values())
    if total_orders <= 0:
        return {
            "available": False,
            "message": "Данные по локальным заказам за период не найдены.",
            "by_region": [],
            "by_sku": [],
            "recommendations": [],
            "diagnostics": {
                "orders_rows_scanned": int(orders_rows_scanned),
                "orders_rows_with_geo": int(orders_rows_with_geo),
                "stock_rows_scanned": int(stock_rows_scanned),
                "stock_rows_with_geo": int(stock_rows_with_geo),
                "required_fields": [
                    "SKU (nmId)",
                    "region/city/warehouse for orders",
                    "orders quantity",
                ],
                "required_source_hint": "WB выгрузка заказов с географией доставки (регион/город) по SKU за период.",
            },
        }

    by_region = []
    for region, region_orders in sorted(total_orders_by_region.items(), key=lambda x: x[1], reverse=True):
        share = (float(region_orders) / float(total_orders)) * 100.0 if total_orders > 0 else 0.0
        by_region.append(
            {
                "region": region,
                "orders": int(region_orders),
                "share_pct": round(share, 1),
                "stock_qty": int(stock_by_region.get(region)) if stock_rows_with_geo > 0 else None,
            }
        )

    by_sku = []
    for sku, sku_orders in sorted(total_orders_by_sku.items(), key=lambda x: x[1], reverse=True):
        regions = []
        for (s, region), region_orders in orders_by_sku_region.items():
            if s != sku:
                continue
            share = (float(region_orders) / float(sku_orders)) * 100.0 if sku_orders > 0 else 0.0
            regions.append(
                {
                    "region": region,
                    "orders": int(region_orders),
                    "share_pct": round(share, 1),
                    "stock_qty": int(stock_by_sku_region.get((sku, region))) if stock_rows_with_geo > 0 else None,
                }
            )
        regions = sorted(regions, key=lambda x: x["orders"], reverse=True)
        by_sku.append(
            {
                "sku": int(sku),
                "total_orders": int(sku_orders),
                "regions": regions[:10],
            }
        )

    low_stock_threshold = max(1, LOCAL_MOVE_MIN_BATCH // 2)
    recommendations: list[dict[str, Any]] = []
    for item in by_sku:
        sku = int(item["sku"])
        sku_orders = int(item["total_orders"])
        actionable = False
        for region_item in item.get("regions", []):
            share_pct = float(region_item.get("share_pct") or 0.0)
            if share_pct < 10.0:
                continue
            region = str(region_item.get("region") or "")
            region_orders = int(region_item.get("orders") or 0)
            stock_qty_raw = region_item.get("stock_qty")
            stock_qty = int(stock_qty_raw) if stock_qty_raw is not None else None
            share = share_pct / 100.0
            recommended_qty = max(int(ceil(float(sku_orders) * share)), int(LOCAL_MOVE_MIN_BATCH))
            if stock_qty is None:
                message = (
                    f"SKU {sku}: за выбранный период {share_pct:.1f}% заказов ({region_orders} шт.) пришлись на {region}. "
                    f"Рекомендуется проверить наличие товара в этом регионе и рассмотреть локальное размещение "
                    f"на уровне {recommended_qty} шт."
                )
                recommendations.append(
                    {
                        "sku": sku,
                        "region": region,
                        "share_pct": round(share_pct, 1),
                        "orders": region_orders,
                        "stock_qty": None,
                        "recommended_qty": int(recommended_qty),
                        "message": message,
                        "priority": "check_stock",
                    }
                )
                actionable = True
                continue

            if stock_qty <= low_stock_threshold:
                stock_text = "остаток 0" if stock_qty == 0 else f"остаток низкий ({stock_qty} шт.)"
                message = (
                    f"SKU {sku}: за выбранный период {share_pct:.1f}% заказов ({region_orders} шт.) пришлись на {region}. "
                    f"В этом регионе {stock_text}. Рекомендуется поставить {recommended_qty} шт."
                )
                recommendations.append(
                    {
                        "sku": sku,
                        "region": region,
                        "share_pct": round(share_pct, 1),
                        "orders": region_orders,
                        "stock_qty": int(stock_qty),
                        "recommended_qty": int(recommended_qty),
                        "message": message,
                        "priority": "move_stock",
                    }
                )
                actionable = True
        if not actionable and item.get("regions"):
            top_region = item["regions"][0]
            recommendations.append(
                {
                    "sku": sku,
                    "region": top_region.get("region"),
                    "share_pct": float(top_region.get("share_pct") or 0.0),
                    "orders": int(top_region.get("orders") or 0),
                    "stock_qty": top_region.get("stock_qty"),
                    "recommended_qty": None,
                    "message": f"SKU {sku}: спрос распределен без выраженного локального дефицита, срочное перемещение не требуется.",
                    "priority": "observe",
                }
            )

    return {
        "available": True,
        "message": "Локальный спрос рассчитан по данным с географией заказов.",
        "by_region": by_region[:20],
        "by_sku": by_sku[:50],
        "recommendations": recommendations[:80],
        "diagnostics": {
            "orders_rows_scanned": int(orders_rows_scanned),
            "orders_rows_with_geo": int(orders_rows_with_geo),
            "stock_rows_scanned": int(stock_rows_scanned),
            "stock_rows_with_geo": int(stock_rows_with_geo),
            "minimal_batch": int(LOCAL_MOVE_MIN_BATCH),
            "low_stock_threshold": int(low_stock_threshold),
            "has_stock_by_region": bool(stock_rows_with_geo > 0),
        },
    }


def _norm_geo_key(value: Any) -> str:
    text = str(value or "").lower().replace("\xa0", " ").strip()
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _build_geo_to_logistics_index(
    flat_reference: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], list[tuple[str, str]]]:
    region_exact: dict[str, str] = {}
    warehouse_exact: dict[str, str] = {}
    alias_pairs: list[tuple[str, str]] = []

    for row in flat_reference:
        region = str(row.get("region") or "").strip()
        warehouse = str(row.get("warehouse") or "").strip()
        if not region:
            continue
        region_key = _norm_geo_key(region)
        if region_key and region_key not in region_exact:
            region_exact[region_key] = region
            alias_pairs.append((region_key, region))
        warehouse_key = _norm_geo_key(warehouse)
        if warehouse_key:
            warehouse_exact[warehouse_key] = region
            alias_pairs.append((warehouse_key, region))

    alias_pairs = sorted(alias_pairs, key=lambda x: len(x[0]), reverse=True)
    return region_exact, warehouse_exact, alias_pairs


def _match_logistics_region(
    geo_label: str,
    *,
    region_exact: dict[str, str],
    warehouse_exact: dict[str, str],
    alias_pairs: list[tuple[str, str]],
) -> tuple[str | None, str]:
    geo_key = _norm_geo_key(geo_label)
    if not geo_key:
        return None, "none"
    if geo_key in region_exact:
        return region_exact[geo_key], "region_exact"
    if geo_key in warehouse_exact:
        return warehouse_exact[geo_key], "warehouse_exact"
    for alias, region in alias_pairs:
        if len(alias) < 5:
            continue
        if alias in geo_key or geo_key in alias:
            return region, "alias_match"
    return None, "unmatched"


def _build_logistics_reference_payload(
    *,
    local_orders_insights: dict[str, Any],
) -> dict[str, Any]:
    reference = load_warehouse_logistics_reference()
    flat_reference = flatten_warehouse_logistics_reference(reference)
    region_summary = build_region_logistics_summary(reference)

    sortable = []
    regions_over_150: list[str] = []
    low_coverage_regions: list[str] = []
    unknown_regions: list[str] = []

    for region, item in region_summary.items():
        avg = _to_float_or_none(item.get("avg_coefficient"))
        known = _to_int(item.get("known_count"))
        unknown = _to_int(item.get("unknown_count"))
        if avg is not None:
            sortable.append((region, float(avg)))
            if float(avg) > float(HIGH_COEFFICIENT_ALERT):
                regions_over_150.append(region)
        else:
            unknown_regions.append(region)
        if known == 0 or (known > 0 and unknown > known):
            low_coverage_regions.append(region)

    top_expensive_regions = [
        {
            "region": region,
            "avg_coefficient": avg,
            "class": str((region_summary.get(region) or {}).get("class") or "unknown"),
        }
        for region, avg in sorted(sortable, key=lambda x: x[1], reverse=True)[:5]
    ]

    region_exact, warehouse_exact, alias_pairs = _build_geo_to_logistics_index(flat_reference)
    locality_signals: list[dict[str, Any]] = []
    by_region = (
        local_orders_insights.get("by_region")
        if isinstance(local_orders_insights.get("by_region"), list)
        else []
    )
    for item in by_region:
        if not isinstance(item, dict):
            continue
        geo_region = str(item.get("region") or "").strip()
        if not geo_region:
            continue
        mapped_region, match_type = _match_logistics_region(
            geo_region,
            region_exact=region_exact,
            warehouse_exact=warehouse_exact,
            alias_pairs=alias_pairs,
        )
        summary = (region_summary.get(mapped_region) or {}) if mapped_region else {}
        avg = _to_float_or_none(summary.get("avg_coefficient"))
        cls = str(summary.get("class") or "unknown")
        non_local_orders = _to_int(
            item.get("non_local_orders")
            or item.get("orders_non_local")
            or item.get("not_local_orders")
        )
        local_orders = _to_int(item.get("local_orders") or item.get("orders_local"))
        comment = ""
        risk_level = "low"
        if cls == "expensive" and non_local_orders > 0:
            comment = (
                "В регионе есть не локальные заказы; при повышенной логистике по сети складов "
                "стоит приоритизировать тест локального размещения малыми партиями."
            )
            risk_level = "high"
        elif cls == "expensive":
            comment = (
                "Регион относится к дорогим по логистике; рекомендации по размещению стоит применять осторожно."
            )
            risk_level = "medium"
        elif cls == "unknown":
            comment = (
                "Для региона коэффициенты логистики по части складов отсутствуют, выводы ограничены."
            )
        else:
            comment = (
                "Логистика региона не выглядит завышенной; можно использовать мягкий сценарий расширения размещения."
            )
        locality_signals.append(
            {
                "geo_region": geo_region,
                "logistics_region": mapped_region,
                "match_type": match_type,
                "orders": _to_int(item.get("orders")),
                "local_orders": local_orders,
                "non_local_orders": non_local_orders,
                "avg_coefficient": avg,
                "logistics_class": cls,
                "risk_level": risk_level,
                "comment": comment,
            }
        )

    potential_risk_regions = [
        row
        for row in locality_signals
        if str(row.get("risk_level")) == "high"
    ][:10]

    return {
        "reference": reference,
        "flat_reference": flat_reference,
        "region_summary": region_summary,
        "top_expensive_regions": top_expensive_regions,
        "regions_over_150": regions_over_150,
        "low_coverage_regions": low_coverage_regions,
        "unknown_regions": unknown_regions,
        "locality_signals": locality_signals,
        "potential_risk_regions": potential_risk_regions,
    }


def _enhance_local_orders_with_logistics(
    *,
    local_orders_insights: dict[str, Any],
    logistics_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(local_orders_insights, dict):
        return {"available": False, "message": "local orders payload is invalid"}

    enhanced = dict(local_orders_insights)
    signals = logistics_payload.get("locality_signals") or []
    if not isinstance(signals, list):
        return enhanced

    signal_by_geo = {
        _norm_geo_key(item.get("geo_region")): item
        for item in signals
        if isinstance(item, dict) and _norm_geo_key(item.get("geo_region"))
    }

    by_region = enhanced.get("by_region")
    if isinstance(by_region, list):
        enriched_regions: list[dict[str, Any]] = []
        for row in by_region:
            if not isinstance(row, dict):
                continue
            key = _norm_geo_key(row.get("region"))
            signal = signal_by_geo.get(key)
            merged = dict(row)
            if isinstance(signal, dict):
                merged["logistics_region"] = signal.get("logistics_region")
                merged["logistics_class"] = signal.get("logistics_class")
                merged["logistics_avg_coefficient"] = signal.get("avg_coefficient")
                merged["logistics_comment"] = signal.get("comment")
            enriched_regions.append(merged)
        enhanced["by_region"] = enriched_regions

    recommendations = enhanced.get("recommendations")
    if isinstance(recommendations, list):
        enriched_recommendations: list[dict[str, Any]] = []
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            out = dict(rec)
            key = _norm_geo_key(rec.get("region"))
            signal = signal_by_geo.get(key)
            if isinstance(signal, dict):
                cls = str(signal.get("logistics_class") or "unknown")
                non_local = _to_int(signal.get("non_local_orders"))
                logistic_note = str(signal.get("comment") or "").strip()
                base_message = str(out.get("message") or "").strip()
                if cls == "expensive" and non_local > 0:
                    out["priority"] = "move_stock_high"
                if logistic_note:
                    if base_message:
                        out["message"] = f"{base_message} {logistic_note}"
                    else:
                        out["message"] = logistic_note
                out["logistics_class"] = cls
                out["logistics_avg_coefficient"] = signal.get("avg_coefficient")
            enriched_recommendations.append(out)
        enhanced["recommendations"] = enriched_recommendations

    return enhanced


def _dedupe_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> tuple[list[dict[str, Any]], int]:
    out: list[dict[str, Any]] = []
    seen = set()
    dup = 0
    for row in rows:
        key = tuple(str(row.get(f, "")) for f in key_fields)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        out.append(row)
    return out, dup


def _audit_stock_summary(
    *,
    stocks_raw: list[dict[str, Any]],
    stocks_parse_diag: dict[str, Any],
    avg_daily_sales: float,
    lead_days: int = 14,
    safety_days: int = 7,
) -> dict[str, Any]:
    total_units = 0
    by_key: dict[str, int] = defaultdict(int)
    parsed_rows = int(stocks_parse_diag.get("parsed_rows") or 0)
    mapped_rows = int(stocks_parse_diag.get("mapped_rows") or 0)

    for r in (stocks_raw or []):
        if not isinstance(r, dict):
            continue
        q = _to_int(r.get("quantityFull") or r.get("quantity") or r.get("qty") or r.get("stock"))
        key = r.get("nmId") or r.get("nm_id") or r.get("supplierArticle") or r.get("vendorCode")
        if key:
            by_key[str(key)] += max(q, 0)
        if q > 0:
            total_units += q

    sku_count = len(by_key)
    days_of_cover = (float(total_units) / float(avg_daily_sales)) if avg_daily_sales else 0.0
    threshold = int(lead_days + safety_days)

    aggregation_status = stocks_parse_diag.get("status") or "unknown"
    if aggregation_status == "ok" and parsed_rows > 0 and total_units == 0:
        aggregation_status = "aggregation_zero_with_nonempty_input"
    if aggregation_status == "ok" and parsed_rows > 0 and mapped_rows == 0:
        aggregation_status = "aggregation_unmapped"

    return {
        "stock_units": int(total_units),
        "sku_count": int(sku_count),
        "days_of_cover": round(float(days_of_cover or 0.0), 2),
        "risk_of_oos": bool(days_of_cover != 0 and days_of_cover < threshold),
        "threshold_days": threshold,
        "items_count": int(len(stocks_raw or [])),
        "by_sku_or_article": by_key,
        "parsed_rows": parsed_rows,
        "mapped_rows": mapped_rows,
        "aggregation_status": aggregation_status,
        "parse_diagnostics": stocks_parse_diag,
        "note": (
            "Остатки собраны из выгрузки файлов. "
            "Если нет Артикул WB, агрегирование идет по артикулу продавца."
        ),
    }


def _build_search_insights(
    *,
    selected_search_files: list[str],
    search_rows: list[dict[str, Any]],
    search_parse_diag: dict[str, Any],
) -> dict[str, Any]:
    if not selected_search_files:
        return {
            "status": "missing",
            "message": "search file not provided",
            "profitable": [],
            "unprofitable": [],
            "potential": [],
            "base_rows": [],
            "parse_diagnostics": search_parse_diag,
        }

    status = str(search_parse_diag.get("status") or "unknown")
    if status != "ok" and not search_rows:
        return {
            "status": status,
            "message": f"search file selected but parse status is {status}",
            "profitable": [],
            "unprofitable": [],
            "potential": [],
            "base_rows": [],
            "parse_diagnostics": search_parse_diag,
        }

    profitable: list[dict[str, Any]] = []
    unprofitable: list[dict[str, Any]] = []
    potential: list[dict[str, Any]] = []
    base_rows: list[dict[str, Any]] = []

    for row in search_rows:
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        impressions = _to_int(row.get("impressions"))
        clicks = _to_int(row.get("clicks"))
        add_to_cart = _to_int(row.get("add_to_cart"))
        orders = _to_int(row.get("orders"))
        buyouts = _to_int(row.get("buyouts"))
        spend = _to_float(row.get("spend"))
        revenue = _to_float(row.get("revenue"))
        ctr = (clicks / impressions) if impressions > 0 else None

        payload = {
            "query": query,
            "impressions": impressions,
            "clicks": clicks,
            "add_to_cart": add_to_cart,
            "orders": orders,
            "buyouts": buyouts,
            "spend": round(spend, 2),
            "revenue": round(revenue, 2),
            "ctr": round(ctr, 4) if ctr is not None else None,
            "nmId": _to_int(row.get("nmId")),
            "seller_article": row.get("seller_article"),
            "roas": round((revenue / spend), 3) if spend > 0 else None,
        }
        base_rows.append(payload)

        if (orders > 0 or buyouts > 0) and (revenue > 0 or spend == 0):
            profitable.append(payload)
        elif (spend > 0 or clicks > 0) and orders == 0 and buyouts == 0:
            unprofitable.append(payload)
        elif impressions > 0 and clicks == 0:
            potential.append(payload)

    final_status = "ok" if base_rows else ("empty_after_parse" if status == "ok" else status)
    return {
        "status": final_status,
        "message": (
            "search parsed"
            if final_status == "ok"
            else f"search file selected but no usable rows (status={final_status})"
        ),
        "profitable": profitable[:200],
        "unprofitable": unprofitable[:200],
        "potential": potential[:200],
        "base_rows": base_rows[:500],
        "summary": {
            "rows_count": len(base_rows),
            "profitable_count": len(profitable),
            "unprofitable_count": len(unprofitable),
            "potential_count": len(potential),
        },
        "parse_diagnostics": search_parse_diag,
    }


def _build_source_consistency_warnings(finance: dict[str, Any], funnel: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    finance_qty = _to_int(finance.get("sales_qty"))
    funnel_buyouts = _to_int(funnel.get("buys"))
    finance_rev = _to_float(finance.get("gross_revenue"))
    funnel_rev = _to_float(funnel.get("revenue_buyouts"))

    def _rel_diff(a: float, b: float) -> float:
        denom = max(abs(a), abs(b), 1.0)
        return abs(a - b) / denom

    if finance_qty > 0 and funnel_buyouts > 0:
        diff = _rel_diff(float(finance_qty), float(funnel_buyouts))
        if diff > 0.5:
            warnings.append(
                {
                    "type": "quantity_mismatch",
                    "severity": "high",
                    "message": "Выкупы по funnel и finance сильно расходятся",
                    "numbers": {
                        "finance_sales_qty": finance_qty,
                        "funnel_buyouts": funnel_buyouts,
                        "relative_diff": round(diff, 4),
                    },
                }
            )
        elif diff > 0.3:
            warnings.append(
                {
                    "type": "quantity_mismatch",
                    "severity": "medium",
                    "message": "Выкупы по funnel и finance заметно расходятся",
                    "numbers": {
                        "finance_sales_qty": finance_qty,
                        "funnel_buyouts": funnel_buyouts,
                        "relative_diff": round(diff, 4),
                    },
                }
            )

    if finance_rev > 0 and funnel_rev > 0:
        diff = _rel_diff(finance_rev, funnel_rev)
        if diff > 0.5:
            warnings.append(
                {
                    "type": "revenue_mismatch",
                    "severity": "high",
                    "message": "Выручка по funnel и finance сильно расходится",
                    "numbers": {
                        "finance_gross_revenue": round(finance_rev, 2),
                        "funnel_revenue_buyouts": round(funnel_rev, 2),
                        "relative_diff": round(diff, 4),
                    },
                }
            )
        elif diff > 0.3:
            warnings.append(
                {
                    "type": "revenue_mismatch",
                    "severity": "medium",
                    "message": "Выручка по funnel и finance заметно расходится",
                    "numbers": {
                        "finance_gross_revenue": round(finance_rev, 2),
                        "funnel_revenue_buyouts": round(funnel_rev, 2),
                        "relative_diff": round(diff, 4),
                    },
                }
            )
    return warnings


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
    source_consistency_warnings: list[dict[str, Any]],
    profit_without_cogs: bool,
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

    if profit_without_cogs:
        reasons.append(
            {
                "category": "finance",
                "reason": "Прибыль рассчитана без COGS (себестоимость не загружена)",
                "numbers": {"profit_without_cogs": True},
            }
        )

    for warning in source_consistency_warnings:
        reasons.append(
            {
                "category": "consistency",
                "reason": warning.get("message"),
                "numbers": warning.get("numbers"),
            }
        )

    stock_aggregation_status = str(stock.get("aggregation_status") or "")
    if stock_aggregation_status not in {"ok", ""}:
        reasons.append(
            {
                "category": "stock",
                "reason": "Проблема агрегации остатков: итоговые метрики могут быть неполными",
                "numbers": {
                    "aggregation_status": stock_aggregation_status,
                    "parsed_rows": stock.get("parsed_rows"),
                    "mapped_rows": stock.get("mapped_rows"),
                },
            }
        )

    negative_margin_sku = finance.get("negative_margin_sku") or []
    unprofitable_sku = [
        {
            "sku": int(x.get("sku") or 0),
            "profit": round(_to_float(x.get("profit")), 2),
            "margin": round(_to_float(x.get("margin")), 4),
        }
        for x in negative_margin_sku[:100]
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
    for row in (search_insights.get("unprofitable") or [])[:200]:
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
    for row in (search_insights.get("profitable") or [])[:50]:
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
            "profit_without_cogs": bool(profit_without_cogs),
        },
        "reasons_of_loss": reasons[:40],
        "unprofitable_sku": unprofitable_sku,
        "sku_without_sales": sku_without_sales[:200],
        "ads_leaks": ads_leaks[:200],
        "dead_stock": dead_stock[:200],
        "growth_points": growth_points[:200],
        "source_consistency_warnings": source_consistency_warnings,
        "missing_data": {
            "required": missing_required,
            "optional": missing_optional,
        },
    }


def _build_actions(decision_layer: dict[str, Any], stock_summary: dict[str, Any]) -> list[dict[str, Any]]:
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
                "numbers": {"profit": kpi.get("profit"), "margin": kpi.get("margin")},
            }
        )

    if kpi.get("profit_without_cogs"):
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Загрузить COGS-файл и пересчитать прибыль с учетом себестоимости",
                "why": "Текущая прибыль рассчитана без себестоимости",
                "expected_effect": "Корректная оценка реальной прибыльности кабинета",
                "numbers": {"profit_without_cogs": True},
            }
        )

    if decision_layer.get("source_consistency_warnings"):
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "action": "Проверить период и полноту weekly finance-файлов относительно funnel",
                "why": "Между funnel и finance есть сильные расхождения",
                "expected_effect": "Согласованные показатели выручки и количества выкупов",
                "numbers": {"warnings_count": len(decision_layer.get("source_consistency_warnings") or [])},
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
                "numbers": {"leaks_count": len(decision_layer.get("ads_leaks") or [])},
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
                "numbers": {"unprofitable_sku_count": len(decision_layer.get("unprofitable_sku") or [])},
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
                "numbers": {"dead_stock_count": len(decision_layer.get("dead_stock") or [])},
            }
        )

    if str(stock_summary.get("aggregation_status") or "") not in {"ok", ""}:
        actions.append(
            {
                "priority": "P1",
                "area": "stock",
                "action": "Перепроверить формат отчета остатков и маппинг колонок",
                "why": "Агрегация остатков отработала с ошибкой/неполным маппингом",
                "expected_effect": "Корректные метрики stock_units, sku_count и days_of_cover",
                "numbers": {
                    "aggregation_status": stock_summary.get("aggregation_status"),
                    "parsed_rows": stock_summary.get("parsed_rows"),
                    "mapped_rows": stock_summary.get("mapped_rows"),
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
                "numbers": {"profit": kpi.get("profit"), "margin": kpi.get("margin")},
            }
        )
    return actions


def _build_inputs_section(
    *,
    input_dir: str,
    detected_files: list[Any],
    grouped_files: dict[str, list[Any]],
    selected_files: dict[str, list[str]],
    missing_required: list[str],
    missing_optional: list[str],
    parse_diagnostics: dict[str, Any],
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

    blocks_collected = [k for k in FILE_TYPES if selected_files.get(k)]
    blocks_skipped = [k for k in FILE_TYPES if k not in blocks_collected]

    candidate_files = {}
    for file_type in FILE_TYPES:
        candidate_files[file_type] = [x.path for x in (grouped_files.get(file_type) or [])]

    return {
        "input_dir": input_dir,
        "found_files": found,
        "candidate_files": candidate_files,
        "selected_files": selected_files,
        "blocks_collected": blocks_collected,
        "blocks_skipped": blocks_skipped,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "parse_diagnostics": parse_diagnostics,
    }


def _parse_many_finance(files: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    diagnostics = []
    for path in files:
        rows, diag = parse_finance_file_with_diagnostics(path)
        rows_all.extend(rows)
        diagnostics.append(diag)

    deduped, dup_count = _dedupe_rows(
        rows_all,
        key_fields=(
            "doc_type_name",
            "nm_id",
            "quantity",
            "retail_amount",
            "ppvz_sales_commission",
            "ppvz_for_pay",
            "delivery_rub",
            "storage_fee",
            "penalty",
            "_supplier_article",
            "_name",
        ),
    )
    return deduped, {
        "files_count": len(files),
        "rows_raw_total": len(rows_all),
        "rows_after_dedup": len(deduped),
        "duplicates_removed": int(dup_count),
        "files": diagnostics,
    }


def _parse_many_ads(files: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_all: list[dict[str, Any]] = []
    diagnostics = []
    for path in files:
        rows, diag = parse_ads_file_with_diagnostics(path)
        rows_all.extend(rows)
        diagnostics.append(diag)

    deduped, dup_count = _dedupe_rows(
        rows_all,
        key_fields=("nmId", "name", "spend", "impressions", "clicks", "revenueAttr"),
    )
    return deduped, {
        "files_count": len(files),
        "rows_raw_total": len(rows_all),
        "rows_after_dedup": len(deduped),
        "duplicates_removed": int(dup_count),
        "files": diagnostics,
    }


def build_audit_facts(input_dir: str = "audit/input", period_label: str = "") -> dict[str, Any]:
    tax_rate = float(os.getenv("WB_TAX_RATE", "0.06"))
    report_date = dt.datetime.now(WB_TIMEZONE).date()

    detected_files = scan_input_files(input_dir)
    grouped_files = group_detected_files(detected_files)

    missing_required = [file_type for file_type in REQUIRED_TYPES if not grouped_files.get(file_type)]
    missing_optional = [file_type for file_type in OPTIONAL_TYPES if not grouped_files.get(file_type)]

    selected_files: dict[str, list[str]] = {
        "finance": [x.path for x in (grouped_files.get("finance") or [])],
        "ads": [x.path for x in (grouped_files.get("ads") or [])],
        "funnel": [grouped_files["funnel"][0].path] if grouped_files.get("funnel") else [],
        "stocks": [grouped_files["stocks"][0].path] if grouped_files.get("stocks") else [],
        "search": [grouped_files["search"][0].path] if grouped_files.get("search") else [],
        "cogs": [grouped_files["cogs"][0].path] if grouped_files.get("cogs") else [],
    }

    finance_rows, finance_parse_diag = _parse_many_finance(selected_files["finance"])
    ads_rows, ads_parse_diag = _parse_many_ads(selected_files["ads"])
    funnel_rows = parse_funnel_file(selected_files["funnel"][0]) if selected_files["funnel"] else []
    stocks_rows, stocks_parse_diag = (
        parse_stocks_file_with_diagnostics(selected_files["stocks"][0]) if selected_files["stocks"] else ([], {"status": "file_not_provided"})
    )
    search_rows, search_parse_diag = (
        parse_search_file_with_diagnostics(selected_files["search"][0]) if selected_files["search"] else ([], {"status": "file_not_provided"})
    )
    cogs_rows = parse_cogs_file(selected_files["cogs"][0]) if selected_files["cogs"] else []

    funnel_summary = calc_funnel_metrics(funnel_rows) if funnel_rows else {}
    financial_summary = calc_financial_metrics(finance_rows, tax_rate=tax_rate) if finance_rows else {"rows_count": 0}
    ads_summary = calc_ads_metrics(ads_rows) if ads_rows else {}
    ads_summary["files_count"] = len(selected_files["ads"])
    ads_summary["parse_diagnostics"] = ads_parse_diag
    financial_summary["files_count"] = len(selected_files["finance"])
    financial_summary["parse_diagnostics"] = finance_parse_diag

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
    stock_summary = _audit_stock_summary(
        stocks_raw=stocks_rows,
        stocks_parse_diag=stocks_parse_diag,
        avg_daily_sales=avg_daily_sales,
    )
    search_insights = _build_search_insights(
        selected_search_files=selected_files["search"],
        search_rows=search_rows,
        search_parse_diag=search_parse_diag,
    )
    local_orders_insights = _build_local_orders_insights(
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
    )
    logistics_payload: dict[str, Any]
    try:
        logistics_payload = _build_logistics_reference_payload(
            local_orders_insights=local_orders_insights,
        )
    except Exception as exc:
        logistics_payload = {
            "reference": {},
            "flat_reference": [],
            "region_summary": {},
            "top_expensive_regions": [],
            "regions_over_150": [],
            "low_coverage_regions": [],
            "unknown_regions": [],
            "locality_signals": [],
            "potential_risk_regions": [],
            "error": f"logistics_payload_failed: {exc}",
        }

    local_orders_insights = _enhance_local_orders_with_logistics(
        local_orders_insights=local_orders_insights,
        logistics_payload=logistics_payload,
    )
    try:
        logistics_formula_model = _build_logistics_formula_model_payload(
            funnel_summary=funnel_summary,
            financial_summary=financial_summary,
            local_orders_insights=local_orders_insights,
            logistics_payload=logistics_payload,
            funnel_rows=funnel_rows,
            stocks_rows=stocks_rows,
            finance_rows=finance_rows,
        )
    except Exception as exc:
        logistics_formula_model = {
            "status": "error",
            "missing_inputs": [],
            "inputs_available": {},
            "explanation": "Расчётная модель логистики не собрана из-за ошибки.",
            "diagnostics": {
                "error": f"logistics_formula_model_failed: {exc}",
            },
        }

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

    profit_without_cogs = len(cogs_rows) == 0
    financial_summary["profit_without_cogs"] = bool(profit_without_cogs)
    financial_summary["profit_label"] = "Прибыль без учета себестоимости" if profit_without_cogs else "Прибыль"
    if profit_without_cogs:
        financial_summary["profit_note"] = "COGS-файл не загружен; показатель прибыли не учитывает себестоимость."

    source_consistency_warnings = _build_source_consistency_warnings(financial_summary, funnel_summary)

    decision_layer = _build_decision_layer(
        finance=financial_summary,
        funnel=funnel_summary,
        ads=ads_summary,
        stock=stock_summary,
        sku_rows=sku_rows,
        search_insights=search_insights,
        missing_required=missing_required,
        missing_optional=missing_optional,
        source_consistency_warnings=source_consistency_warnings,
        profit_without_cogs=profit_without_cogs,
    )
    actions = _build_actions(decision_layer, stock_summary)

    parse_diagnostics = {
        "finance": finance_parse_diag,
        "ads": ads_parse_diag,
        "stocks": stocks_parse_diag,
        "search": search_parse_diag,
    }
    audit_period = _derive_audit_period(
        period_label=period_label,
        report_date=report_date,
        selected_files=selected_files,
        parse_diagnostics=parse_diagnostics,
        period_days=period_days,
    )

    inputs = _build_inputs_section(
        input_dir=input_dir,
        detected_files=detected_files,
        grouped_files=grouped_files,
        selected_files=selected_files,
        missing_required=missing_required,
        missing_optional=missing_optional,
        parse_diagnostics=parse_diagnostics,
    )

    return {
        "date": _iso(report_date),
        "report_type": "audit",
        "source": "wb",
        "timezone": str(WB_TIMEZONE),
        "tax_rate": tax_rate,
        "period": {
            "label": period_label or _iso(report_date),
            "days": int(period_days),
        },
        "audit_period": audit_period,
        "inputs": inputs,
        "financial_summary": financial_summary,
        "funnel_summary": funnel_summary,
        "ads_summary": ads_summary,
        "stock_summary": stock_summary,
        "search_insights": search_insights,
        "local_orders_insights": local_orders_insights,
        "logistics_reference": {
            "regions": logistics_payload.get("reference") or {},
            "rows": logistics_payload.get("flat_reference") or [],
            "regions_count": len(logistics_payload.get("reference") or {}),
            "warehouses_count": len(logistics_payload.get("flat_reference") or []),
            "source": "static_json",
            "source_path": "shared/data/warehouse_logistics_coefficients.json",
        },
        "region_logistics_summary": logistics_payload.get("region_summary") or {},
        "top_expensive_logistics_regions": logistics_payload.get("top_expensive_regions") or [],
        "logistics_regions_over_150": logistics_payload.get("regions_over_150") or [],
        "logistics_regions_low_coverage": logistics_payload.get("low_coverage_regions") or [],
        "logistics_regions_unknown": logistics_payload.get("unknown_regions") or [],
        "logistics_locality_signals": logistics_payload.get("locality_signals") or [],
        "logistics_potential_risk_regions": logistics_payload.get("potential_risk_regions") or [],
        "logistics_diagnostics": {
            "error": str(logistics_payload.get("error") or ""),
        },
        "logistics_formula_model": logistics_formula_model,
        "cogs_input": {
            "rows_count": len(cogs_rows),
            "rows": cogs_rows[:200],
            "loaded": bool(cogs_rows),
        },
        "sku_profit": sku_profit,
        "abc_analysis": (sku_performance.get("abc_summary") if isinstance(sku_performance, dict) else {}) or {},
        "decision_layer": decision_layer,
        "actions": actions,
        "source_consistency_warnings": source_consistency_warnings,
        "notes": [
            "Аудит собран из файлов в audit/input без WB API.",
            "При отсутствии части файлов аудит строится по доступным данным и помечается как partial.",
            "Обязательные блоки: finance, funnel, stocks. Опциональные: ads, search, cogs.",
        ],
    }
