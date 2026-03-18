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

    funnel_block = _funnel_snapshot(metrics)
    metrics["funnel"] = funnel_block

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
    diagnostics = _dict_or_empty(metrics.get("diagnostics"))
    diagnostics.update(
        {
            "has_daily_report": bool(sales_rows_count > 0),
            "has_funnel": bool(_has_funnel_data(funnel_block)),
            "rows": {
                "sales_rows": int(sales_rows_count),
                "ads_rows": int(ads_rows_count),
                "stocks_rows": int(stocks_rows_count),
                "orders_api_rows": int(len(bundle.orders_api)),
                "sales_api_rows": int(len(bundle.sales_api)),
                "realization_api_rows": int(len(bundle.realization_api)),
                "supplier_goods_financial_rows": int(len(bundle.supplier_goods_financial)),
            },
        }
    )
    metrics["diagnostics"] = diagnostics
    return metrics
