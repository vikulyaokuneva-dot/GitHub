from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Tuple


_CYRILLIC_IO = "\u0451"
_CYRILLIC_E = "\u0435"


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace(" ", "").replace(",", ".")
    try:
        return float(candidate)
    except ValueError:
        return None


def _safe_positive(value: Any) -> float:
    parsed = _as_float_or_none(value)
    if parsed is None:
        return 0.0
    return max(0.0, float(parsed))


def _resolve_qty(row: Mapping[str, Any], keys: Iterable[str]) -> float:
    for key in keys:
        parsed = _as_float_or_none(row.get(key))
        if parsed is not None:
            return max(0.0, float(parsed))
    return 0.0


def _resolve_sku(value: Any) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", token):
        return token.split(".", 1)[0]
    return token.lower().replace(_CYRILLIC_IO, _CYRILLIC_E).strip()


def _resolve_warehouse_token(value: Any) -> str:
    token = str(value or "").strip().lower().replace(_CYRILLIC_IO, _CYRILLIC_E)
    token = re.sub(r"[^a-z\u0430-\u044f0-9]+", " ", token)
    token = re.sub(r"\s+", " ", token).strip()
    return token


def _resolve_warehouse_from_row(row: Mapping[str, Any]) -> str:
    for key in ("warehouse", "warehouse_name", "stock_warehouse", "office", "office_name"):
        token = _resolve_warehouse_token(row.get(key))
        if token:
            return token
    return ""


def _resolve_region_from_row(row: Mapping[str, Any]) -> str:
    for key in (
        "region",
        "region_name",
        "regionName",
        "destination",
        "destination_region",
        "destinationRegion",
        "oblastOkrugName",
        "warehouse_region",
        "warehouseRegion",
    ):
        token = _resolve_warehouse_token(row.get(key))
        if token:
            return token
    return ""


def _extract_rows(source: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
    if isinstance(source, list):
        return [row for row in source if isinstance(row, dict)]
    if not isinstance(source, dict):
        return []
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def extract_sku_metrics(metrics: Any) -> List[Dict[str, Any]]:
    rows = _extract_rows(metrics, ("sku_metrics", "items", "skus"))
    return rows


def build_sku_metrics_index(metrics: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in extract_sku_metrics(metrics):
        sku = _resolve_sku(row.get("sku") or row.get("nm_id") or row.get("offer_id"))
        if sku:
            out[sku] = row
    return out


def _build_sku_alias_map(sales_rows: List[Dict[str, Any]], known_skus: set[str]) -> Dict[str, str]:
    weighted_links: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in sales_rows:
        sku = _resolve_sku(row.get("sku"))
        seller_sku = _resolve_sku(row.get("seller_sku"))
        if not sku:
            continue
        qty = _resolve_qty(row, ("buys", "sales_count", "orders", "quantity"))
        weight = qty if qty > 0 else 1.0
        weighted_links[sku][sku] += weight
        if seller_sku:
            weighted_links[seller_sku][sku] += weight

    alias_map: Dict[str, str] = {}
    for alias, links in weighted_links.items():
        if not links:
            continue
        alias_map[alias] = max(links.items(), key=lambda item: item[1])[0]
    for sku in known_skus:
        alias_map.setdefault(sku, sku)
    return alias_map


def extract_demand_by_warehouse(sales_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    demand: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in sales_rows:
        sku = _resolve_sku(row.get("sku"))
        if not sku:
            continue
        warehouse = _resolve_warehouse_from_row(row)
        if not warehouse:
            continue
        qty = _resolve_qty(row, ("buys", "sales_count", "orders", "quantity"))
        if qty <= 0:
            continue
        demand[sku][warehouse] += qty
    return {sku: dict(values) for sku, values in demand.items()}


def extract_demand_by_region(sales_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    demand: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in sales_rows:
        sku = _resolve_sku(row.get("sku"))
        if not sku:
            continue
        region = _resolve_region_from_row(row)
        if not region:
            continue
        qty = _resolve_qty(row, ("buys", "sales_count", "orders", "quantity"))
        if qty <= 0:
            continue
        demand[sku][region] += qty
    return {sku: dict(values) for sku, values in demand.items()}


def _extract_stock_map_from_row(row: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    raw_map = row.get("stock_by_warehouse")
    if isinstance(raw_map, dict):
        for warehouse_raw, value in raw_map.items():
            warehouse = _resolve_warehouse_token(warehouse_raw)
            stock_value = _as_float_or_none(value)
            if warehouse and stock_value is not None and stock_value > 0:
                out[warehouse] = out.get(warehouse, 0.0) + float(stock_value)
        if out:
            return out

    warehouse = _resolve_warehouse_from_row(row)
    stock = _resolve_qty(row, ("stock", "qty", "quantity", "stock_qty"))
    if warehouse and stock > 0:
        out[warehouse] = stock
    return out


def _extract_stock_region_map_from_row(row: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    raw_map = row.get("stock_by_region")
    if isinstance(raw_map, dict):
        for region_raw, value in raw_map.items():
            region = _resolve_warehouse_token(region_raw)
            stock_value = _as_float_or_none(value)
            if region and stock_value is not None and stock_value > 0:
                out[region] = out.get(region, 0.0) + float(stock_value)
        if out:
            return out

    region = _resolve_region_from_row(row)
    stock = _resolve_qty(row, ("stock", "qty", "quantity", "stock_qty"))
    if region and stock > 0:
        out[region] = stock
    return out


def extract_stock_by_warehouse(
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None,
    sku_alias_map: Dict[str, str] | None = None,
) -> Dict[str, Dict[str, float]]:
    rows = _extract_rows(stocks_raw, ("stocks_rows", "items", "rows"))
    aliases = sku_alias_map or {}
    stock_by_sku: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        sku = ""
        for key in ("sku", "seller_sku", "nm_id", "nmid", "vendor_code", "offer_id"):
            token = _resolve_sku(row.get(key))
            if not token:
                continue
            sku = aliases.get(token, token)
            if sku:
                break
        if not sku:
            continue

        by_wh = _extract_stock_map_from_row(row)
        if not by_wh:
            continue
        for warehouse, qty in by_wh.items():
            stock_by_sku[sku][warehouse] += float(qty)

    return {sku: dict(values) for sku, values in stock_by_sku.items()}


def extract_stock_by_region(
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None,
    sku_alias_map: Dict[str, str] | None = None,
) -> Dict[str, Dict[str, float]]:
    rows = _extract_rows(stocks_raw, ("stocks_rows", "items", "rows"))
    aliases = sku_alias_map or {}
    stock_by_sku: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        sku = ""
        for key in ("sku", "seller_sku", "nm_id", "nmid", "vendor_code", "offer_id"):
            token = _resolve_sku(row.get(key))
            if not token:
                continue
            sku = aliases.get(token, token)
            if sku:
                break
        if not sku:
            continue

        by_region = _extract_stock_region_map_from_row(row)
        if not by_region:
            continue
        for region, qty in by_region.items():
            stock_by_sku[sku][region] += float(qty)

    return {sku: dict(values) for sku, values in stock_by_sku.items()}


def share_by_warehouse(values: Mapping[str, Any]) -> Dict[str, float]:
    total = sum(max(0.0, _safe_positive(v)) for v in values.values())
    if total <= 0:
        return {}
    out: Dict[str, float] = {}
    for warehouse, value in values.items():
        qty = _safe_positive(value)
        if qty <= 0:
            continue
        out[str(warehouse)] = round(qty / total, 6)
    return out


def compute_locality_score(demand_share: Mapping[str, Any], stock_share: Mapping[str, Any]) -> float:
    warehouses = set(demand_share.keys()) | set(stock_share.keys())
    if not warehouses:
        return 0.0
    score = 0.0
    for warehouse in warehouses:
        demand = _safe_positive(demand_share.get(warehouse))
        stock = _safe_positive(stock_share.get(warehouse))
        score += min(demand, stock)
    return max(0.0, min(1.0, round(score, 6)))


def compute_distribution_gap(demand_share: Mapping[str, Any], stock_share: Mapping[str, Any]) -> float:
    warehouses = set(demand_share.keys()) | set(stock_share.keys())
    if not warehouses:
        return 0.0
    return round(
        0.5
        * sum(
            abs(_safe_positive(demand_share.get(warehouse)) - _safe_positive(stock_share.get(warehouse)))
            for warehouse in warehouses
        ),
        6,
    )


def dominant_warehouses(share_map: Mapping[str, Any], threshold: float = 0.2) -> List[str]:
    rows: List[tuple[str, float]] = []
    for warehouse, value in share_map.items():
        share = _as_float_or_none(value)
        if share is None or share <= threshold:
            continue
        rows.append((str(warehouse), float(share)))
    rows.sort(key=lambda item: (-item[1], item[0]))
    return [warehouse for warehouse, _ in rows]


def _top_concentration(
    values: Mapping[str, Any],
    shares: Mapping[str, Any],
    *,
    top_n: int = 3,
    key_name: str = "region",
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for token, qty_raw in values.items():
        qty = _safe_positive(qty_raw)
        if qty <= 0:
            continue
        share_pct = _safe_positive(shares.get(token)) * 100.0
        rows.append(
            {
                key_name: str(token),
                "value": round(qty, 6),
                "share_pct": round(share_pct, 4),
            }
        )
    rows.sort(key=lambda item: (-float(item.get("share_pct", 0.0) or 0.0), -float(item.get("value", 0.0) or 0.0), str(item.get(key_name) or "")))
    return rows[: max(1, int(top_n))]


def _resolve_confidence(total_orders: float, *, min_orders_for_confidence: int, localization_known: bool) -> str:
    if total_orders <= 0 or not localization_known:
        return "low"
    if total_orders < max(1, int(min_orders_for_confidence)):
        return "low"
    if total_orders < 10:
        return "medium"
    return "high"


def _resolve_total_orders(sku_metric_row: Mapping[str, Any], demand_total: float) -> float:
    candidates = ("orders", "orders_count", "sales_count", "buys", "total_orders")
    for key in candidates:
        parsed = _as_float_or_none(sku_metric_row.get(key))
        if parsed is not None:
            return max(0.0, float(parsed))
    return max(0.0, float(demand_total))


def _resolve_explicit_local_orders(sku_metric_row: Mapping[str, Any]) -> float | None:
    for key in ("local_orders", "orders_local", "localized_orders"):
        parsed = _as_float_or_none(sku_metric_row.get(key))
        if parsed is not None:
            return max(0.0, float(parsed))
    return None


def _resolve_analysis_mode(
    *,
    valid_sku_attribution: bool,
    order_count_available: bool,
    demand_geography_available: bool,
    stock_geography_available: bool,
    minimum_sample_met: bool,
    localization_known: bool,
) -> tuple[str, str, str]:
    if not valid_sku_attribution:
        return "disabled", "blocked_by_data", "blocked_by_data"
    if not order_count_available:
        return "disabled", "insufficient_data", "blocked_by_data"
    if not demand_geography_available:
        return "disabled", "insufficient_data", "blocked_by_data"
    if not localization_known:
        return "preview", "insufficient_data", "watch"
    if not stock_geography_available:
        return "preview", "insufficient_data", "watch"
    if not minimum_sample_met:
        return "preview", "low_confidence", "watch"
    return "full", "ok", "actionable"


def _resolve_blocked_reasons(
    *,
    valid_sku_attribution: bool,
    order_count_available: bool,
    demand_geography_available: bool,
    stock_geography_available: bool,
    minimum_sample_met: bool,
    localization_known: bool,
) -> List[str]:
    reasons: List[str] = []
    if not valid_sku_attribution:
        reasons.append("sku_attribution_broken")
    if not order_count_available:
        reasons.append("missing_order_count")
    if not demand_geography_available:
        reasons.append("missing_demand_geography")
    if not stock_geography_available:
        reasons.append("missing_stock_geography")
    if order_count_available and not minimum_sample_met:
        reasons.append("insufficient_order_volume")
    if not localization_known:
        reasons.append("localization_not_computable")
    return reasons


def _resolve_analysis_status(*, analysis_mode: str, recommendation_status: str) -> str:
    mode = str(analysis_mode or "disabled").strip().lower()
    recommendation = str(recommendation_status or "blocked_by_data").strip().lower()
    if mode == "full" and recommendation == "actionable":
        return "usable"
    if mode == "preview" or recommendation == "watch":
        return "preview"
    if recommendation == "blocked_by_data":
        return "blocked_by_data"
    return "disabled"


def build_localization_rows(
    metrics: Dict[str, Any],
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None = None,
    *,
    min_orders_for_confidence: int = 3,
    min_orders_for_actionable: int = 5,
    sku_attribution_status: str = "ok",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    warnings: List[Dict[str, str]] = []

    sku_metrics_index = build_sku_metrics_index(metrics)
    sales_rows = _extract_rows(metrics, ("sales_rows", "sales_raw", "raw_sales_rows", "sales_report_rows"))

    demand_by_sku = extract_demand_by_warehouse(sales_rows)
    demand_region_by_sku = extract_demand_by_region(sales_rows)
    alias_map = _build_sku_alias_map(sales_rows, set(sku_metrics_index.keys()))
    stock_rows_source = stocks_raw if stocks_raw is not None else (metrics.get("stocks_rows") if isinstance(metrics, dict) else None)
    stock_by_sku = extract_stock_by_warehouse(stock_rows_source, sku_alias_map=alias_map)
    stock_region_by_sku = extract_stock_by_region(stock_rows_source, sku_alias_map=alias_map)

    known_skus = set(sku_metrics_index.keys()) | set(demand_by_sku.keys()) | set(stock_by_sku.keys())
    rows: List[Dict[str, Any]] = []

    if not known_skus:
        warnings.append(
            {
                "code": "territorial_distribution_sku_missing",
                "message": "No SKU rows available for territorial distribution analysis.",
            }
        )
        return rows, warnings

    attribution_ok = str(sku_attribution_status or "ok").strip().lower() != "broken"

    for sku in sorted(known_skus):
        metric_row = sku_metrics_index.get(sku, {})
        demand_map = demand_by_sku.get(sku, {})
        demand_region_map = demand_region_by_sku.get(sku, {})
        stock_map = stock_by_sku.get(sku, {})
        stock_region_map = stock_region_by_sku.get(sku, {})
        output_sku = str(metric_row.get("sku") or sku).strip() if isinstance(metric_row, dict) else sku
        if not output_sku:
            output_sku = sku

        demand_total = sum(_safe_positive(v) for v in demand_map.values())
        total_orders = _resolve_total_orders(metric_row, demand_total)

        demand_share = share_by_warehouse(demand_map)
        stock_share = share_by_warehouse(stock_map)
        demand_region_share = share_by_warehouse(demand_region_map)
        stock_region_share = share_by_warehouse(stock_region_map)
        locality_score = compute_locality_score(demand_share, stock_share)

        explicit_local_orders = _resolve_explicit_local_orders(metric_row)
        demand_geography_available = bool(demand_map) or explicit_local_orders is not None
        stock_geography_available = bool(stock_map)
        order_count_available = bool(total_orders > 0)
        minimum_sample_met = bool(total_orders >= max(1, int(min_orders_for_actionable)))
        valid_sku_attribution = bool(attribution_ok and output_sku)

        local_orders: float | None
        localization_share: float | None
        local_orders_source: str

        if explicit_local_orders is not None and total_orders > 0:
            local_orders = min(total_orders, max(0.0, explicit_local_orders))
            localization_share = round(local_orders / total_orders * 100.0, 6)
            local_orders_source = "input_local_orders"
        elif total_orders > 0 and demand_geography_available and stock_geography_available:
            local_orders = round(total_orders * locality_score, 6)
            localization_share = round(local_orders / total_orders * 100.0, 6)
            local_orders_source = "estimated_from_warehouse_shares"
        elif total_orders <= 0:
            local_orders = 0.0
            localization_share = None
            local_orders_source = "not_applicable_no_orders"
        else:
            local_orders = None
            localization_share = None
            local_orders_source = "unavailable"

        localization_known = localization_share is not None
        analysis_mode, data_quality_status, recommendation_status = _resolve_analysis_mode(
            valid_sku_attribution=valid_sku_attribution,
            order_count_available=order_count_available,
            demand_geography_available=demand_geography_available,
            stock_geography_available=stock_geography_available,
            minimum_sample_met=minimum_sample_met,
            localization_known=localization_known,
        )

        confidence = _resolve_confidence(
            total_orders,
            min_orders_for_confidence=min_orders_for_confidence,
            localization_known=localization_known,
        )
        blocked_reasons = _resolve_blocked_reasons(
            valid_sku_attribution=valid_sku_attribution,
            order_count_available=order_count_available,
            demand_geography_available=demand_geography_available,
            stock_geography_available=stock_geography_available,
            minimum_sample_met=minimum_sample_met,
            localization_known=localization_known,
        )
        analysis_status = _resolve_analysis_status(
            analysis_mode=analysis_mode,
            recommendation_status=recommendation_status,
        )

        distribution_gap = compute_distribution_gap(demand_share, stock_share) if demand_share or stock_share else None
        non_local_orders: float | None
        non_local_share_pct: float | None
        if local_orders is not None and total_orders > 0:
            non_local_orders = round(max(0.0, total_orders - float(local_orders)), 6)
            non_local_share_pct = round(max(0.0, 100.0 - float(localization_share or 0.0)), 6)
        else:
            non_local_orders = None
            non_local_share_pct = None

        unavailable_metrics: List[str] = []
        if not demand_geography_available:
            unavailable_metrics.append("demand_geography")
        if not stock_geography_available:
            unavailable_metrics.append("stock_geography")
        if not localization_known:
            unavailable_metrics.append("localization_share")

        estimated_metrics: Dict[str, Any] = {}
        if local_orders_source == "estimated_from_warehouse_shares":
            estimated_metrics["local_orders"] = local_orders
            estimated_metrics["localization_share"] = localization_share

        known_facts: Dict[str, Any] = {
            "total_orders": round(total_orders, 6),
            "demand_warehouses_count": len(demand_map),
            "stock_warehouses_count": len(stock_map),
            "demand_regions_count": len(demand_region_map),
            "stock_regions_count": len(stock_region_map),
        }
        if local_orders_source == "input_local_orders":
            known_facts["local_orders"] = round(float(local_orders or 0.0), 6)
            known_facts["localization_share"] = localization_share

        suppressed_recommendations: List[str] = []
        if recommendation_status != "actionable":
            suppressed_recommendations.extend(["rebalance_stock", "relocate_inventory"])

        rows.append(
            {
                "sku": output_sku,
                "total_orders": round(total_orders, 6),
                "local_orders": (round(float(local_orders), 6) if local_orders is not None else None),
                "localization_share": localization_share,
                "confidence": confidence,
                "analysis_status": analysis_status,
                "blocked_reasons": blocked_reasons,
                "low_sample_warning": total_orders < max(1, int(min_orders_for_confidence)),
                "demand_by_warehouse": {k: round(_safe_positive(v), 6) for k, v in demand_map.items()},
                "stock_by_warehouse": {k: round(_safe_positive(v), 6) for k, v in stock_map.items()},
                "demand_share_by_warehouse": demand_share,
                "stock_share_by_warehouse": stock_share,
                "demand_by_region": {k: round(_safe_positive(v), 6) for k, v in demand_region_map.items()},
                "stock_by_region": {k: round(_safe_positive(v), 6) for k, v in stock_region_map.items()},
                "demand_share_by_region": demand_region_share,
                "stock_share_by_region": stock_region_share,
                "top_demand_regions": _top_concentration(demand_region_map, demand_region_share, top_n=3, key_name="region"),
                "top_supply_regions": _top_concentration(stock_region_map, stock_region_share, top_n=3, key_name="region"),
                "distribution_gap": distribution_gap,
                "locality_score": locality_score,
                "dominant_demand_warehouses": dominant_warehouses(demand_share),
                "dominant_stock_warehouses": dominant_warehouses(stock_share),
                "non_local_orders_estimate": non_local_orders,
                "non_local_share_pct": non_local_share_pct,
                "local_orders_source": local_orders_source,
                "source_metric_row": metric_row if isinstance(metric_row, dict) else {},
                "valid_sku_attribution": valid_sku_attribution,
                "order_count_available": order_count_available,
                "demand_geography_available": demand_geography_available,
                "stock_geography_available": stock_geography_available,
                "minimum_sample_met": minimum_sample_met,
                "analysis_mode": analysis_mode,
                "data_quality_status": data_quality_status,
                "recommendation_status": recommendation_status,
                "evidence_sources": {
                    "local_orders": local_orders_source,
                    "demand_geography": "sales_rows" if bool(demand_map) else ("explicit_local_orders" if explicit_local_orders is not None else "missing"),
                    "stock_geography": "stocks_rows" if bool(stock_map) else "missing",
                    "demand_regions": "sales_rows_region_fields" if bool(demand_region_map) else "missing",
                    "stock_regions": "stocks_rows_region_fields" if bool(stock_region_map) else "missing",
                    "sku_attribution": "metrics_data_quality",
                },
                "known_facts": known_facts,
                "estimated_metrics": estimated_metrics,
                "unavailable_metrics": unavailable_metrics,
                "suppressed_recommendations": suppressed_recommendations,
                "blocked_reason_details": {
                    "valid_sku_attribution": bool(valid_sku_attribution),
                    "order_count_available": bool(order_count_available),
                    "demand_geography_available": bool(demand_geography_available),
                    "stock_geography_available": bool(stock_geography_available),
                    "minimum_sample_met": bool(minimum_sample_met),
                    "minimum_orders_required": int(max(1, int(min_orders_for_actionable))),
                    "total_orders": round(total_orders, 6),
                    "localization_known": bool(localization_known),
                },
            }
        )

    if not sales_rows:
        warnings.append(
            {
                "code": "territorial_distribution_sales_rows_missing",
                "message": "Sales rows are missing for robust localization estimation.",
            }
        )
    if not stock_by_sku:
        warnings.append(
            {
                "code": "territorial_distribution_stock_rows_missing",
                "message": "Stock rows are missing for robust localization estimation.",
            }
        )
    rows_with_blocked_demand_geo = sum(1 for row in rows if isinstance(row, dict) and "missing_demand_geography" in list(row.get("blocked_reasons", [])))
    rows_with_blocked_stock_geo = sum(1 for row in rows if isinstance(row, dict) and "missing_stock_geography" in list(row.get("blocked_reasons", [])))
    if rows_with_blocked_demand_geo > 0:
        warnings.append(
            {
                "code": "territorial_distribution_demand_geo_partial",
                "message": f"Demand geography is missing for {rows_with_blocked_demand_geo} SKU rows.",
            }
        )
    if rows_with_blocked_stock_geo > 0:
        warnings.append(
            {
                "code": "territorial_distribution_stock_geo_partial",
                "message": f"Stock geography is missing for {rows_with_blocked_stock_geo} SKU rows.",
            }
        )

    return rows, warnings
