from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..raw.models import RawIngestionBundle
from .models import (
    NormalizedAdsRow,
    NormalizedBundle,
    NormalizedOrderRow,
    NormalizedSalesRow,
    NormalizedStockRow,
    NormalizedSupplierGoodsFinancialRow,
)


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _first_non_empty(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return value
    return ""


def _to_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_orders_rows(rows: List[Dict[str, Any]]) -> List[NormalizedOrderRow]:
    out: List[NormalizedOrderRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            NormalizedOrderRow(
                date=_to_str(_first_non_empty(row, ("date", "lastChangeDate", "createdAt"))),
                sku=_to_str(_first_non_empty(row, ("sku", "supplierArticle", "vendorCode"))),
                nm_id=_to_str(_first_non_empty(row, ("nm_id", "nmId", "nmid"))),
                order_id=_to_str(_first_non_empty(row, ("order_id", "srid", "srid2", "rid"))),
                quantity=_safe_float(_first_non_empty(row, ("quantity", "qty", "count")) or 1.0),
                price=_safe_float(
                    _first_non_empty(row, ("price", "finishedPrice", "priceWithDisc", "totalPrice", "revenue"))
                ),
                warehouse=_to_str(_first_non_empty(row, ("warehouse", "warehouseName", "warehouse_name"))),
                raw=dict(row),
            )
        )
    return out


def _normalize_sales_rows(rows: List[Dict[str, Any]]) -> List[NormalizedSalesRow]:
    out: List[NormalizedSalesRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        orders_value = _safe_float(_first_non_empty(row, ("orders", "order_count", "orders_count", "ordered_quantity")))
        buys_value = _safe_float(_first_non_empty(row, ("buys", "sales_count", "quantity", "count", "orders")))
        quantity_value = _safe_float(_first_non_empty(row, ("quantity", "count", "qty", "buys", "sales_count", "orders")))
        out.append(
            NormalizedSalesRow(
                date=_to_str(_first_non_empty(row, ("date", "lastChangeDate", "saleDate", "createdAt"))),
                sku=_to_str(_first_non_empty(row, ("sku", "seller_sku", "supplierArticle", "vendorCode"))),
                nm_id=_to_str(_first_non_empty(row, ("nm_id", "nmId", "nmid"))),
                order_ref=_to_str(_first_non_empty(row, ("order_ref", "order_id", "srid", "saleID", "gNumber"))),
                quantity=quantity_value,
                revenue=_safe_float(_first_non_empty(row, ("revenue", "forPay", "finishedPrice", "priceWithDisc", "totalPrice"))),
                buys=buys_value,
                orders=orders_value,
                cost_price=_safe_float(_first_non_empty(row, ("cost_price", "cogs", "cost"))),
                wb_commission=_safe_float(_first_non_empty(row, ("wb_commission", "commission", "retail_commission"))),
                logistics=_safe_float(_first_non_empty(row, ("logistics", "deliveryRub", "delivery_cost"))),
                storage=_safe_float(_first_non_empty(row, ("storage", "storage_cost"))),
                penalties=_safe_float(_first_non_empty(row, ("penalties", "penalty", "fine"))),
                deductions=_safe_float(_first_non_empty(row, ("deductions", "deduction"))),
                ads_spend=_safe_float(_first_non_empty(row, ("ads_spend", "ad_cost", "ads"))),
                profit=_safe_float(_first_non_empty(row, ("profit",))),
                warehouse=_to_str(_first_non_empty(row, ("warehouse", "warehouseName", "warehouse_name"))),
                raw=dict(row),
            )
        )
    return out


def _normalize_stocks_rows(rows: List[Dict[str, Any]]) -> List[NormalizedStockRow]:
    out: List[NormalizedStockRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            NormalizedStockRow(
                sku=_to_str(_first_non_empty(row, ("sku", "seller_sku", "supplierArticle", "vendorCode"))),
                nm_id=_to_str(_first_non_empty(row, ("nm_id", "nmId", "nmid"))),
                quantity=_safe_float(_first_non_empty(row, ("stock", "quantity", "qty", "amount"))),
                warehouse=_to_str(_first_non_empty(row, ("warehouse", "warehouseName", "warehouse_name"))),
                raw=dict(row),
            )
        )
    return out


def _normalize_ads_rows(rows: List[Dict[str, Any]]) -> List[NormalizedAdsRow]:
    out: List[NormalizedAdsRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            NormalizedAdsRow(
                date=_to_str(_first_non_empty(row, ("date", "day", "report_date"))),
                sku=_to_str(_first_non_empty(row, ("sku", "seller_sku", "supplierArticle", "vendorCode"))),
                nm_id=_to_str(_first_non_empty(row, ("nm_id", "nmId", "nmid"))),
                spend=_safe_float(_first_non_empty(row, ("ads_spend", "spend", "cost", "sum"))),
                impressions=_safe_float(_first_non_empty(row, ("impressions", "shows", "views"))),
                clicks=_safe_float(_first_non_empty(row, ("clicks",))),
                orders=_safe_float(_first_non_empty(row, ("orders", "sales_count", "buys"))),
                revenue=_safe_float(_first_non_empty(row, ("revenue", "orders_revenue"))),
                is_campaign_total=bool(row.get("_is_campaign_total", False)),
                raw=dict(row),
            )
        )
    return out


def _normalize_supplier_goods_financial_rows(supplier_goods_daily: Dict[str, Any]) -> List[NormalizedSupplierGoodsFinancialRow]:
    if not isinstance(supplier_goods_daily, dict) or not bool(supplier_goods_daily.get("found", False)):
        return []
    row = NormalizedSupplierGoodsFinancialRow(
        sku="",
        nm_id="",
        revenue_to_transfer=_safe_float(
            supplier_goods_daily.get("buyouts_amount", supplier_goods_daily.get("orders_amount", 0.0))
        ),
        wb_commission=_safe_float(supplier_goods_daily.get("wb_commission", 0.0)),
        logistics=_safe_float(supplier_goods_daily.get("logistics", 0.0)),
        storage=_safe_float(supplier_goods_daily.get("storage", 0.0)),
        deductions=_safe_float(supplier_goods_daily.get("deductions", 0.0)),
        returns_qty=_safe_float(supplier_goods_daily.get("returns_qty", 0.0)),
        source_file=_to_str(supplier_goods_daily.get("source_file")),
        is_aggregate=True,
        raw=dict(supplier_goods_daily),
    )
    return [row]


def normalize_raw_bundle(raw_bundle: RawIngestionBundle) -> NormalizedBundle:
    sales = _normalize_sales_rows(raw_bundle.sales_rows)
    ads = _normalize_ads_rows(raw_bundle.ads_rows)
    stocks = _normalize_stocks_rows(raw_bundle.stocks_rows)
    orders_api = _normalize_orders_rows(raw_bundle.api_orders_rows)
    sales_api = _normalize_sales_rows(raw_bundle.api_sales_rows)
    realization_api = _normalize_sales_rows(raw_bundle.api_realization_rows)
    stocks_api = _normalize_stocks_rows(raw_bundle.api_stocks_rows)
    supplier_financial_rows = _normalize_supplier_goods_financial_rows(raw_bundle.supplier_goods_daily)

    return NormalizedBundle(
        source_mode=str(raw_bundle.source_mode or ""),
        sales=sales,
        ads=ads,
        stocks=stocks,
        orders_api=orders_api,
        sales_api=sales_api,
        realization_api=realization_api,
        stocks_api=stocks_api,
        supplier_goods_financial=supplier_financial_rows,
        debug={
            "sales_rows_normalized": len(sales),
            "ads_rows_normalized": len(ads),
            "stocks_rows_normalized": len(stocks),
            "orders_api_rows_normalized": len(orders_api),
            "sales_api_rows_normalized": len(sales_api),
            "realization_api_rows_normalized": len(realization_api),
            "supplier_goods_financial_rows_normalized": len(supplier_financial_rows),
        },
    )
