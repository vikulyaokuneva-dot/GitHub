from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..normalization.models import (
    NormalizedAdsRow,
    NormalizedBundle,
    NormalizedOrderRow,
    NormalizedSalesRow,
    NormalizedStockRow,
)
from ..sources.wb_reports_loader import build_metrics_from_reports as build_legacy_metrics_from_reports


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _date_iso(value: Any) -> str:
    token = _to_text(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", token):
        return token[:10]
    return token


def _sku_key(value: Any) -> str:
    token = _to_text(value)
    if not token:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", token):
        return token.split(".", 1)[0]
    return token.lower()


def _first_text(row: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for key in keys:
        value = _to_text(row.get(key))
        if value:
            return value
    return ""


def _to_metrics_sales_rows(rows: List[NormalizedSalesRow]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row.raw or {})
        payload["date"] = row.date
        payload["sku"] = row.sku
        payload["nm_id"] = row.nm_id
        payload["order_ref"] = row.order_ref
        payload["quantity"] = float(row.quantity)
        payload["revenue"] = float(row.revenue)
        payload["buys"] = float(row.buys)
        payload["orders"] = float(row.orders)
        payload["cost_price"] = float(row.cost_price)
        payload["wb_commission"] = float(row.wb_commission)
        payload["logistics"] = float(row.logistics)
        payload["storage"] = float(row.storage)
        payload["penalties"] = float(row.penalties)
        payload["deductions"] = float(row.deductions)
        payload["ads_spend"] = float(row.ads_spend)
        payload["profit"] = float(row.profit)
        payload["warehouse"] = row.warehouse
        out.append(payload)
    return out


def _to_metrics_ads_rows(rows: List[NormalizedAdsRow]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row.raw or {})
        payload["date"] = row.date
        payload["sku"] = row.sku
        payload["nm_id"] = row.nm_id
        payload["ads_spend"] = float(row.spend)
        payload["impressions"] = float(row.impressions)
        payload["clicks"] = float(row.clicks)
        payload["orders"] = float(row.orders)
        payload["revenue"] = float(row.revenue)
        payload["_is_campaign_total"] = bool(row.is_campaign_total)
        out.append(payload)
    return out


def _to_metrics_stock_rows(rows: List[NormalizedStockRow]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row.raw or {})
        payload["sku"] = row.sku
        payload["nm_id"] = row.nm_id
        payload["stock"] = float(row.quantity)
        payload["warehouse"] = row.warehouse
        out.append(payload)
    return out


def _to_orders_rows_from_api(rows: List[NormalizedOrderRow]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row.raw or {})
        warehouse = _to_text(row.warehouse or raw.get("warehouseName") or raw.get("officeName"))
        region = _first_text(
            raw,
            (
                "region",
                "regionName",
                "destinationRegion",
                "oblastOkrugName",
                "countryName",
            ),
        )
        destination = _first_text(
            raw,
            (
                "destination",
                "destinationRegion",
                "destinationCountry",
                "address",
                "oblastOkrugName",
            ),
        )
        demand_geography_available = bool(region or destination or warehouse)
        out.append(
            {
                "date": _date_iso(row.date or raw.get("date") or raw.get("lastChangeDate")),
                "sku": _to_text(row.sku),
                "nm_id": _to_text(row.nm_id),
                "seller_sku": _first_text(raw, ("seller_sku", "sellerSku", "supplierArticle", "vendorCode")),
                "order_id": _to_text(row.order_id or raw.get("srid") or raw.get("orderId")),
                "order_count": max(0.0, _safe_float(row.quantity)),
                "quantity": max(0.0, _safe_float(row.quantity)),
                "orders_count": max(0.0, _safe_float(row.quantity)),
                "order_amount": max(0.0, _safe_float(row.price)),
                "price": max(0.0, _safe_float(row.price)),
                "warehouse": warehouse,
                "warehouse_name": warehouse,
                "region": region,
                "destination": destination,
                "locality_marker": _to_text(raw.get("localityMarker")),
                "demand_geography_available": demand_geography_available,
                "geo_quality_flag": "ok" if demand_geography_available else "missing_geo_fields",
                "source_dataset": "orders_api",
                "source_contract": "orders_rows_from_api",
                "raw": raw,
            }
        )
    return out


def _aggregate_funnel_rows_from_api(
    *,
    orders_rows: List[NormalizedOrderRow],
    sales_rows: List[NormalizedSalesRow],
) -> List[Dict[str, Any]]:
    bucket: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def _ensure(date: str, sku: str, nm_id: str) -> Dict[str, Any]:
        key = (date, sku, nm_id)
        if key not in bucket:
            bucket[key] = {
                "date": date,
                "sku": sku,
                "nm_id": nm_id,
                "seller_sku": "",
                "orders_count": 0.0,
                "buyouts_count": 0.0,
                "sales_count": 0.0,
                "order_amount": 0.0,
                "buyout_amount": 0.0,
                "views": None,
                "add_to_cart": None,
                "_source_markers": set(),
            }
        return bucket[key]

    for row in orders_rows:
        raw = dict(row.raw or {})
        date = _date_iso(row.date or raw.get("date") or raw.get("lastChangeDate"))
        sku = _to_text(row.sku)
        nm_id = _to_text(row.nm_id)
        if not (sku or nm_id):
            continue
        item = _ensure(date, sku, nm_id)
        item["seller_sku"] = _to_text(item.get("seller_sku")) or _first_text(
            raw,
            ("seller_sku", "sellerSku", "supplierArticle", "vendorCode"),
        )
        item["orders_count"] += max(0.0, _safe_float(row.quantity))
        item["order_amount"] += max(0.0, _safe_float(row.price))
        item["_source_markers"].add("orders_api")
        if item.get("views") is None:
            item["views"] = _safe_float_or_none(raw.get("views"))
        if item.get("add_to_cart") is None:
            item["add_to_cart"] = _safe_float_or_none(raw.get("addToCart") or raw.get("add_to_cart"))

    for row in sales_rows:
        raw = dict(row.raw or {})
        date = _date_iso(row.date or raw.get("date") or raw.get("lastChangeDate"))
        sku = _to_text(row.sku)
        nm_id = _to_text(row.nm_id)
        if not (sku or nm_id):
            continue
        item = _ensure(date, sku, nm_id)
        item["seller_sku"] = _to_text(item.get("seller_sku")) or _first_text(
            raw,
            ("seller_sku", "sellerSku", "supplierArticle", "vendorCode"),
        )
        buyouts_qty = max(0.0, _safe_float(row.buys if _safe_float(row.buys) > 0 else row.quantity))
        item["buyouts_count"] += buyouts_qty
        item["sales_count"] += buyouts_qty
        item["buyout_amount"] += max(0.0, _safe_float(row.revenue))
        item["_source_markers"].add("sales_api")
        if item.get("views") is None:
            item["views"] = _safe_float_or_none(raw.get("views"))
        if item.get("add_to_cart") is None:
            item["add_to_cart"] = _safe_float_or_none(raw.get("addToCart") or raw.get("add_to_cart"))

    out: List[Dict[str, Any]] = []
    for _, row in sorted(bucket.items(), key=lambda item: item[0]):
        orders_count = max(0.0, _safe_float(row.get("orders_count")))
        buyouts_count = max(0.0, _safe_float(row.get("buyouts_count")))
        views = _safe_float_or_none(row.get("views"))
        add_to_cart = _safe_float_or_none(row.get("add_to_cart"))
        upper_funnel_available = bool((views is not None and views > 0) or (add_to_cart is not None and add_to_cart > 0))
        lower_funnel_available = bool(orders_count > 0 or buyouts_count > 0)
        out.append(
            {
                "date": _to_text(row.get("date")),
                "sku": _to_text(row.get("sku")),
                "nm_id": _to_text(row.get("nm_id")),
                "seller_sku": _to_text(row.get("seller_sku")),
                "orders_count": round(orders_count, 6),
                "buyouts_count": round(buyouts_count, 6),
                "sales_count": round(max(0.0, _safe_float(row.get("sales_count"))), 6),
                "order_amount": round(max(0.0, _safe_float(row.get("order_amount"))), 2),
                "buyout_amount": round(max(0.0, _safe_float(row.get("buyout_amount"))), 2),
                "views": round(views, 6) if views is not None else None,
                "add_to_cart": round(add_to_cart, 6) if add_to_cart is not None else None,
                "upper_funnel_available": upper_funnel_available,
                "lower_funnel_available": lower_funnel_available,
                "upper_funnel_unavailable_from_api": bool(lower_funnel_available and not upper_funnel_available),
                "source_markers": sorted(str(marker) for marker in row.get("_source_markers", set())),
                "quality_flags": {
                    "upper_funnel_available": upper_funnel_available,
                    "lower_funnel_available": lower_funnel_available,
                },
                "source_contract": "funnel_rows_from_api",
            }
        )
    return out


def _coverage_pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(float(part) / float(total) * 100.0, 2)


def _build_api_funnel_contract_diagnostics(
    *,
    funnel_rows_from_api: List[Dict[str, Any]],
    orders_rows_from_api: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rows_total = len(orders_rows_from_api)
    rows_with_region = sum(1 for row in orders_rows_from_api if _to_text((row or {}).get("region")))
    rows_with_warehouse = sum(1 for row in orders_rows_from_api if _to_text((row or {}).get("warehouse")))
    rows_with_demand_geo = sum(1 for row in orders_rows_from_api if bool((row or {}).get("demand_geography_available")))

    upper_available = any(
        (
            _safe_float_or_none((row or {}).get("views")) is not None
            and _safe_float((row or {}).get("views")) > 0
        )
        or (
            _safe_float_or_none((row or {}).get("add_to_cart")) is not None
            and _safe_float((row or {}).get("add_to_cart")) > 0
        )
        for row in funnel_rows_from_api
        if isinstance(row, dict)
    )
    lower_available = any(
        _safe_float((row or {}).get("orders_count")) > 0 or _safe_float((row or {}).get("buyouts_count")) > 0
        for row in funnel_rows_from_api
        if isinstance(row, dict)
    )

    missing_geo_fields: List[str] = []
    if rows_with_region <= 0:
        missing_geo_fields.append("region")
    if rows_with_warehouse <= 0:
        missing_geo_fields.append("warehouse")

    if lower_available and upper_available:
        source = "api.orders_sales_ads"
    elif lower_available:
        source = "api.orders_sales"
    elif upper_available:
        source = "api.upper_only"
    else:
        source = "missing"

    return {
        "source": source,
        "funnel_rows_from_api": int(len(funnel_rows_from_api)),
        "orders_rows_from_api": int(rows_total),
        "upper_funnel_available": bool(upper_available),
        "lower_funnel_available": bool(lower_available),
        "upper_funnel_unavailable_from_api": bool(lower_available and not upper_available),
        "degradation_mode": "upper_funnel_unavailable_from_api" if (lower_available and not upper_available) else "none",
        "geo_completeness": {
            "rows_total": int(rows_total),
            "rows_with_region": int(rows_with_region),
            "rows_with_warehouse": int(rows_with_warehouse),
            "rows_with_demand_geography": int(rows_with_demand_geo),
            "region_coverage_pct": _coverage_pct(rows_with_region, rows_total),
            "warehouse_coverage_pct": _coverage_pct(rows_with_warehouse, rows_total),
            "demand_geography_coverage_pct": _coverage_pct(rows_with_demand_geo, rows_total),
        },
        "geo_fields_available": [field for field in ("region", "warehouse") if field not in missing_geo_fields],
        "geo_fields_missing": missing_geo_fields,
    }


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _funnel_snapshot(metrics: Dict[str, Any]) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    sales_funnel = safe_metrics.get("sales_funnel")
    if isinstance(sales_funnel, dict):
        embedded = sales_funnel.get("funnel")
        if isinstance(embedded, dict):
            return dict(embedded)
    funnel = safe_metrics.get("funnel")
    return dict(funnel) if isinstance(funnel, dict) else {}


def _has_funnel_data(funnel: Dict[str, Any]) -> bool:
    if not isinstance(funnel, dict) or not funnel:
        return False
    for key in ("views", "add_to_cart", "orders", "buyouts", "view_to_order_conversion", "buyout_rate"):
        if funnel.get(key) is not None:
            return True
    return False


def _index_sku_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = _sku_key(row.get("sku"))
        nm_id = _sku_key(row.get("nm_id"))
        if sku:
            index[sku] = row
        if nm_id and nm_id not in index:
            index[nm_id] = row
    return index


def _merge_lower_funnel_into_sku_metrics(
    *,
    sku_metrics: List[Dict[str, Any]],
    funnel_rows_from_api: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(sku_metrics, list):
        sku_metrics = []

    rows = [row for row in sku_metrics if isinstance(row, dict)]
    index = _index_sku_metrics(rows)

    for funnel_row in funnel_rows_from_api:
        if not isinstance(funnel_row, dict):
            continue
        sku_key = _sku_key(funnel_row.get("sku"))
        nm_key = _sku_key(funnel_row.get("nm_id"))
        target = index.get(sku_key) or index.get(nm_key)
        if target is None:
            target = {
                "sku": _to_text(funnel_row.get("sku") or funnel_row.get("nm_id")),
                "nm_id": _to_text(funnel_row.get("nm_id")),
                "views": None,
                "add_to_cart": None,
                "orders": 0.0,
                "buys": 0.0,
                "buyouts": 0.0,
                "sales_count": 0.0,
                "revenue": 0.0,
                "ads_spend": 0.0,
            }
            rows.append(target)
            index = _index_sku_metrics(rows)

        api_orders = max(0.0, _safe_float(funnel_row.get("orders_count")))
        api_buyouts = max(0.0, _safe_float(funnel_row.get("buyouts_count")))
        api_buyout_amount = max(0.0, _safe_float(funnel_row.get("buyout_amount")))

        current_orders = max(0.0, _safe_float(target.get("orders")))
        current_buyouts = max(
            0.0,
            _safe_float(
                target.get(
                    "buyouts",
                    target.get("buys", target.get("sales_count", 0.0)),
                )
            ),
        )
        current_revenue = max(0.0, _safe_float(target.get("revenue")))

        if current_orders <= 0 and api_orders > 0:
            target["orders"] = api_orders
            target["orders_count"] = api_orders
            target["ordered_units"] = api_orders

        if current_buyouts <= 0 and api_buyouts > 0:
            target["buyouts"] = api_buyouts
            target["buys"] = api_buyouts
            target["sales_count"] = api_buyouts
            target["buyouts_count"] = api_buyouts

        if current_revenue <= 0 and api_buyout_amount > 0:
            target["revenue"] = api_buyout_amount

        target["api_lower_funnel_orders"] = api_orders
        target["api_lower_funnel_buyouts"] = api_buyouts
        target["api_lower_funnel_source"] = "funnel_rows_from_api"
        target["api_lower_funnel_merged"] = True

    return rows


def build_metrics_from_normalized(bundle: NormalizedBundle) -> Dict[str, Any]:
    sales_rows = _to_metrics_sales_rows(bundle.sales)
    ads_rows = _to_metrics_ads_rows(bundle.ads)
    stocks_rows = _to_metrics_stock_rows(bundle.stocks)
    orders_rows_from_api = _to_orders_rows_from_api(bundle.orders_api)
    funnel_rows_from_api = _aggregate_funnel_rows_from_api(
        orders_rows=bundle.orders_api,
        sales_rows=bundle.sales_api,
    )

    metrics = build_legacy_metrics_from_reports(sales_rows, ads_rows, stocks_rows)
    if not isinstance(metrics, dict):
        metrics = {}
    layer_trace = metrics.get("layer_trace", {})
    if not isinstance(layer_trace, dict):
        layer_trace = {}
    layer_trace.update(
        {
            "raw_to_normalized": True,
            "normalized_to_metrics": True,
            "normalized_counts": dict(bundle.debug or {}),
        }
    )
    metrics["layer_trace"] = layer_trace

    financial_kpi = _dict_or_empty(metrics.get("financial_kpi"))
    financial_block = _dict_or_empty(metrics.get("financial"))
    if not financial_block:
        financial_block = {
            "revenue": financial_kpi.get("revenue"),
            "seller_payout": financial_kpi.get("seller_payout"),
            "commission": financial_kpi.get("wb_commission"),
            "logistics": financial_kpi.get("logistics"),
            "ads": financial_kpi.get("ads_spend"),
            "profit": financial_kpi.get("net_profit"),
            "financial_status": financial_kpi.get("financial_status"),
            "financial_partial": financial_kpi.get("financial_partial"),
        }
    else:
        financial_block.setdefault("revenue", financial_kpi.get("revenue"))
        financial_block.setdefault("seller_payout", financial_kpi.get("seller_payout"))
        financial_block.setdefault("commission", financial_kpi.get("wb_commission"))
        financial_block.setdefault("logistics", financial_kpi.get("logistics"))
        financial_block.setdefault("ads", financial_kpi.get("ads_spend"))
        financial_block.setdefault("profit", financial_kpi.get("net_profit"))
        financial_block.setdefault("financial_status", financial_kpi.get("financial_status"))
        financial_block.setdefault("financial_partial", financial_kpi.get("financial_partial"))
    metrics["financial"] = financial_block

    sku_metrics = metrics.get("sku_metrics", [])
    if not isinstance(sku_metrics, list):
        sku_metrics = []
    metrics["sku_metrics"] = _merge_lower_funnel_into_sku_metrics(
        sku_metrics=sku_metrics,
        funnel_rows_from_api=funnel_rows_from_api,
    )

    funnel_block = _funnel_snapshot(metrics)
    metrics["funnel"] = funnel_block
    metrics["funnel_rows_from_api"] = funnel_rows_from_api
    metrics["orders_rows_from_api"] = orders_rows_from_api

    ads_block = _dict_or_empty(metrics.get("ads"))
    if not ads_block:
        ads_summary = _dict_or_empty(metrics.get("ads_diagnostics"))
        ads_block = {
            "spend": financial_kpi.get("ads_spend"),
            "rows": len(ads_rows),
            "diagnostics": ads_summary,
        }
    metrics["ads"] = ads_block

    sales_rows_count = len(sales_rows)
    ads_rows_count = len(ads_rows)
    stocks_rows_count = len(stocks_rows)
    api_funnel_diag = _build_api_funnel_contract_diagnostics(
        funnel_rows_from_api=funnel_rows_from_api,
        orders_rows_from_api=orders_rows_from_api,
    )
    diagnostics = _dict_or_empty(metrics.get("diagnostics"))
    diagnostics.update(
        {
            "has_daily_report": bool(sales_rows_count > 0),
            "has_funnel": bool(_has_funnel_data(funnel_block) or bool(api_funnel_diag.get("lower_funnel_available", False))),
            "rows": {
                "sales_rows": int(sales_rows_count),
                "ads_rows": int(ads_rows_count),
                "stocks_rows": int(stocks_rows_count),
                "orders_api_rows": int(len(bundle.orders_api)),
                "sales_api_rows": int(len(bundle.sales_api)),
                "realization_api_rows": int(len(bundle.realization_api)),
                "supplier_goods_financial_rows": int(len(bundle.supplier_goods_financial)),
                "funnel_rows_from_api": int(len(funnel_rows_from_api)),
                "orders_rows_from_api": int(len(orders_rows_from_api)),
            },
            "api_funnel_contract": api_funnel_diag,
        }
    )
    metrics["diagnostics"] = diagnostics
    return metrics
