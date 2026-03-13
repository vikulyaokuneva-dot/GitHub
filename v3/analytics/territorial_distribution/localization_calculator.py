from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Tuple



_CYRILLIC_IO = '\u0451'

_CYRILLIC_E = '\u0435'


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace(' ', '').replace(',', '.')
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
    token = str(value or '').strip()
    if not token:
        return ''
    if re.fullmatch(r'\d+(\.0+)?', token):
        return token.split('.', 1)[0]
    return token.lower().replace(_CYRILLIC_IO, _CYRILLIC_E).strip()


def _resolve_warehouse_token(value: Any) -> str:
    token = str(value or '').strip().lower().replace(_CYRILLIC_IO, _CYRILLIC_E)
    token = re.sub(r'[^a-z\u0430-\u044f0-9]+', ' ', token)
    token = re.sub(r'\s+', ' ', token).strip()
    return token


def _resolve_warehouse_from_row(row: Mapping[str, Any]) -> str:
    for key in ('warehouse', 'warehouse_name', 'stock_warehouse', 'office', 'office_name'):
        token = _resolve_warehouse_token(row.get(key))
        if token:
            return token
    return ''


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
    rows = _extract_rows(metrics, ('sku_metrics', 'items', 'skus'))
    return rows


def build_sku_metrics_index(metrics: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in extract_sku_metrics(metrics):
        sku = _resolve_sku(row.get('sku') or row.get('nm_id') or row.get('offer_id'))
        if sku:
            out[sku] = row
    return out


def _build_sku_alias_map(sales_rows: List[Dict[str, Any]], known_skus: set[str]) -> Dict[str, str]:
    weighted_links: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in sales_rows:
        sku = _resolve_sku(row.get('sku'))
        seller_sku = _resolve_sku(row.get('seller_sku'))
        if not sku:
            continue
        qty = _resolve_qty(row, ('buys', 'sales_count', 'orders', 'quantity'))
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
        sku = _resolve_sku(row.get('sku'))
        if not sku:
            continue
        warehouse = _resolve_warehouse_from_row(row)
        if not warehouse:
            continue
        qty = _resolve_qty(row, ('buys', 'sales_count', 'orders', 'quantity'))
        if qty <= 0:
            continue
        demand[sku][warehouse] += qty
    return {sku: dict(values) for sku, values in demand.items()}


def _extract_stock_map_from_row(row: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    raw_map = row.get('stock_by_warehouse')
    if isinstance(raw_map, dict):
        for warehouse_raw, value in raw_map.items():
            warehouse = _resolve_warehouse_token(warehouse_raw)
            stock_value = _as_float_or_none(value)
            if warehouse and stock_value is not None and stock_value > 0:
                out[warehouse] = out.get(warehouse, 0.0) + float(stock_value)
        if out:
            return out

    warehouse = _resolve_warehouse_from_row(row)
    stock = _resolve_qty(row, ('stock', 'qty', 'quantity', 'stock_qty'))
    if warehouse and stock > 0:
        out[warehouse] = stock
    return out


def extract_stock_by_warehouse(
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None,
    sku_alias_map: Dict[str, str] | None = None,
) -> Dict[str, Dict[str, float]]:
    rows = _extract_rows(stocks_raw, ('stocks_rows', 'items', 'rows'))
    aliases = sku_alias_map or {}
    stock_by_sku: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        sku = ''
        for key in ('sku', 'seller_sku', 'nm_id', 'nmid', 'vendor_code', 'offer_id'):
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
        0.5 * sum(abs(_safe_positive(demand_share.get(warehouse)) - _safe_positive(stock_share.get(warehouse))) for warehouse in warehouses),
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


def _resolve_confidence(total_orders: float) -> str:
    if total_orders < 3:
        return 'low'
    if total_orders < 10:
        return 'medium'
    return 'high'


def _resolve_total_orders(sku_metric_row: Mapping[str, Any], demand_total: float) -> float:
    candidates = ('orders', 'orders_count', 'sales_count', 'buys', 'total_orders')
    for key in candidates:
        parsed = _as_float_or_none(sku_metric_row.get(key))
        if parsed is not None:
            return max(0.0, float(parsed))
    return max(0.0, float(demand_total))


def _resolve_explicit_local_orders(sku_metric_row: Mapping[str, Any]) -> float | None:
    for key in ('local_orders', 'orders_local', 'localized_orders'):
        parsed = _as_float_or_none(sku_metric_row.get(key))
        if parsed is not None:
            return max(0.0, float(parsed))
    return None


def build_localization_rows(
    metrics: Dict[str, Any],
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    warnings: List[Dict[str, str]] = []

    sku_metrics_index = build_sku_metrics_index(metrics)
    sales_rows = _extract_rows(metrics, ('sales_rows', 'sales_raw', 'raw_sales_rows', 'sales_report_rows'))

    demand_by_sku = extract_demand_by_warehouse(sales_rows)
    alias_map = _build_sku_alias_map(sales_rows, set(sku_metrics_index.keys()))
    stock_rows_source = stocks_raw if stocks_raw is not None else (metrics.get('stocks_rows') if isinstance(metrics, dict) else None)
    stock_by_sku = extract_stock_by_warehouse(stock_rows_source, sku_alias_map=alias_map)

    known_skus = set(sku_metrics_index.keys()) | set(demand_by_sku.keys()) | set(stock_by_sku.keys())
    rows: List[Dict[str, Any]] = []

    if not known_skus:
        warnings.append({'code': 'territorial_distribution_sku_missing', 'message': 'No SKU rows available for territorial distribution analysis.'})
        return rows, warnings

    for sku in sorted(known_skus):
        metric_row = sku_metrics_index.get(sku, {})
        demand_map = demand_by_sku.get(sku, {})
        stock_map = stock_by_sku.get(sku, {})
        output_sku = str(metric_row.get('sku') or sku).strip() if isinstance(metric_row, dict) else sku
        if not output_sku:
            output_sku = sku
        demand_total = sum(_safe_positive(v) for v in demand_map.values())
        total_orders = _resolve_total_orders(metric_row, demand_total)

        demand_share = share_by_warehouse(demand_map)
        stock_share = share_by_warehouse(stock_map)
        locality_score = compute_locality_score(demand_share, stock_share)
        explicit_local_orders = _resolve_explicit_local_orders(metric_row)
        if explicit_local_orders is None:
            local_orders = round(total_orders * locality_score, 6)
            local_orders_source = 'estimated_from_warehouse_shares'
        else:
            local_orders = min(total_orders, max(0.0, explicit_local_orders))
            local_orders_source = 'input_local_orders'

        if total_orders > 0:
            localization_share = round(local_orders / total_orders * 100.0, 6)
        else:
            localization_share = None

        distribution_gap = compute_distribution_gap(demand_share, stock_share) if demand_share or stock_share else None

        rows.append(
            {
                'sku': output_sku,
                'total_orders': round(total_orders, 6),
                'local_orders': round(local_orders, 6),
                'localization_share': localization_share,
                'confidence': _resolve_confidence(total_orders),
                'low_sample_warning': total_orders < 3,
                'demand_by_warehouse': {k: round(_safe_positive(v), 6) for k, v in demand_map.items()},
                'stock_by_warehouse': {k: round(_safe_positive(v), 6) for k, v in stock_map.items()},
                'demand_share_by_warehouse': demand_share,
                'stock_share_by_warehouse': stock_share,
                'distribution_gap': distribution_gap,
                'locality_score': locality_score,
                'dominant_demand_warehouses': dominant_warehouses(demand_share),
                'dominant_stock_warehouses': dominant_warehouses(stock_share),
                'local_orders_source': local_orders_source,
                'source_metric_row': metric_row if isinstance(metric_row, dict) else {},
            }
        )

    if not sales_rows:
        warnings.append({'code': 'territorial_distribution_sales_rows_missing', 'message': 'Sales rows are missing for robust localization estimation.'})
    if not stock_by_sku:
        warnings.append({'code': 'territorial_distribution_stock_rows_missing', 'message': 'Stock rows are missing for robust localization estimation.'})

    return rows, warnings



