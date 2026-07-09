from __future__ import annotations

from typing import Any, Dict, List

from ..api.endpoints import STOCKS_OFFICES, STOCKS_PRODUCTS, STOCKS_WB_WAREHOUSES
from ..api.wb_client import WBApiClient


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def load_stocks_wb_warehouses(client: WBApiClient) -> Dict[str, Any]:
    """Current stocks from WB warehouses (updates every 30 min)."""
    body = {"skipDeletedNm": True}

    try:
        result = client.request_json(
            endpoint=STOCKS_WB_WAREHOUSES,
            method="POST",
            json_body=body,
            allow_204=True,
            empty_on_204=[],
        )
    except Exception as exc:
        return {"rows": [], "available": False, "api_debug": {"success": False, "error_text": str(exc)[:500]}}

    payload = result.get("payload", result)
    data = payload.get("data", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []

    rows: List[Dict[str, Any]] = []
    for item in (data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        nm_id = _safe_int(item.get("nmId") or item.get("nm_id"))
        if not nm_id:
            continue
        warehouse = _safe_text(item.get("warehouseName") or item.get("warehouse"))
        region = _safe_text(item.get("regionName") or item.get("region"))
        quantity = _safe_float(item.get("quantity") or item.get("quantityFull"))
        in_transit = _safe_float(item.get("inWayToClient"))
        returns = _safe_float(item.get("inWayFromClient"))

        rows.append({
            "nm_id": nm_id,
            "sku": str(nm_id),
            "warehouse": warehouse,
            "region": region,
            "quantity": round(quantity, 2),
            "in_transit_to_client": round(in_transit, 2),
            "in_transit_from_client": round(returns, 2),
            "total_stock": round(quantity + in_transit, 2),
            "_source_dataset": "stocks_wb_warehouses",
        })

    return {
        "rows": rows,
        "available": bool(rows),
        "api_debug": {
            "endpoint": "stocks_wb_warehouses",
            "success": result.get("success", bool(rows)),
            "rows_loaded": len(rows),
        },
    }


def load_stocks_products(client: WBApiClient, *, nm_ids: List[int] | None = None) -> Dict[str, Any]:
    """Per-product stocks with turnover, lostOrders, lostBuyouts."""
    body: Dict[str, Any] = {
        "stockType": "wb",
        "limit": 100,
        "offset": 0,
    }
    if nm_ids:
        body["nmIDs"] = nm_ids

    try:
        result = client.request_json(
            endpoint=STOCKS_PRODUCTS,
            method="POST",
            json_body=body,
            allow_204=True,
            empty_on_204=[],
        )
    except Exception as exc:
        return {"rows": [], "available": False, "api_debug": {"success": False, "error_text": str(exc)[:500]}}

    payload = result.get("payload", result)
    data = payload.get("data", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []

    rows: List[Dict[str, Any]] = []
    for item in (data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        nm_id = _safe_int(item.get("nmId") or item.get("nm_id"))
        if not nm_id:
            continue

        stock_qty = _safe_float(item.get("stock") or item.get("quantity") or item.get("quantityFull"))
        stock_cost = _safe_float(item.get("stockCost") or item.get("stock_cost"))
        sale_rate = _safe_float(item.get("saleRate") or item.get("sale_rate"))
        turnover_days = _safe_float(item.get("turnoverDays") or item.get("turnover_days"))
        lost_orders = _safe_int(item.get("lostOrdersCount") or item.get("lost_orders_count"))
        lost_buyouts = _safe_int(item.get("lostBuyoutsCount") or item.get("lost_buyouts_count"))
        price = _safe_float(item.get("price") or item.get("basicPrice") or item.get("retailPrice"))
        orders_count = _safe_int(item.get("ordersCount") or item.get("orders_count"))
        buyouts_count = _safe_int(item.get("buyoutsCount") or item.get("buyouts_count"))
        stock_status = _safe_text(item.get("status") or item.get("stockStatus"))

        rows.append({
            "nm_id": nm_id,
            "sku": str(nm_id),
            "stock_quantity": round(stock_qty, 2),
            "stock_cost": round(stock_cost, 2),
            "sale_rate": round(sale_rate, 2),
            "turnover_days": round(turnover_days, 1),
            "lost_orders_count": lost_orders,
            "lost_buyouts_count": lost_buyouts,
            "price": round(price, 2),
            "orders_count": orders_count,
            "buyouts_count": buyouts_count,
            "stock_status": stock_status,
            "_source_dataset": "stocks_products",
        })

    return {
        "rows": rows,
        "available": bool(rows),
        "api_debug": {
            "endpoint": "stocks_products",
            "success": result.get("success", bool(rows)),
            "rows_loaded": len(rows),
        },
    }


def load_stocks_offices(client: WBApiClient, *, nm_ids: List[int] | None = None) -> Dict[str, Any]:
    """Stocks by warehouses/regions with saleRate."""
    body: Dict[str, Any] = {
        "stockType": "wb",
        "limit": 100,
        "offset": 0,
    }
    if nm_ids:
        body["nmIDs"] = nm_ids

    try:
        result = client.request_json(
            endpoint=STOCKS_OFFICES,
            method="POST",
            json_body=body,
            allow_204=True,
            empty_on_204=[],
        )
    except Exception as exc:
        return {"rows": [], "available": False, "api_debug": {"success": False, "error_text": str(exc)[:500]}}

    payload = result.get("payload", result)
    data = payload.get("data", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []

    rows: List[Dict[str, Any]] = []
    for item in (data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        nm_id = _safe_int(item.get("nmId") or item.get("nm_id"))
        if not nm_id:
            continue

        warehouse = _safe_text(item.get("officeName") or item.get("warehouseName") or item.get("warehouse"))
        region = _safe_text(item.get("regionName") or item.get("region"))
        quantity = _safe_float(item.get("quantity") or item.get("quantityFull"))
        sale_rate = _safe_float(item.get("saleRate") or item.get("sale_rate"))
        to_client = _safe_float(item.get("toClientCount") or item.get("to_client_count"))
        from_client = _safe_float(item.get("fromClientCount") or item.get("from_client_count"))

        rows.append({
            "nm_id": nm_id,
            "sku": str(nm_id),
            "warehouse": warehouse,
            "region": region,
            "quantity": round(quantity, 2),
            "sale_rate": round(sale_rate, 2),
            "to_client_count": round(to_client, 2),
            "from_client_count": round(from_client, 2),
            "_source_dataset": "stocks_offices",
        })

    return {
        "rows": rows,
        "available": bool(rows),
        "api_debug": {
            "endpoint": "stocks_offices",
            "success": result.get("success", bool(rows)),
            "rows_loaded": len(rows),
        },
    }
