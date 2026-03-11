from __future__ import annotations

from typing import Any, Dict, List

from ..normalization.models import (
    NormalizedAdsRow,
    NormalizedBundle,
    NormalizedSalesRow,
    NormalizedStockRow,
)
from ..sources.wb_reports_loader import build_metrics_from_reports as build_legacy_metrics_from_reports


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


def build_metrics_from_normalized(bundle: NormalizedBundle) -> Dict[str, Any]:
    sales_rows = _to_metrics_sales_rows(bundle.sales)
    ads_rows = _to_metrics_ads_rows(bundle.ads)
    stocks_rows = _to_metrics_stock_rows(bundle.stocks)
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
    return metrics
