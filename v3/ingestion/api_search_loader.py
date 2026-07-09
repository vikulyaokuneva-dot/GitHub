from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..api.endpoints import SEARCH_PRODUCT_ORDERS, SEARCH_PRODUCT_TEXTS
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


def load_search_product_texts(
    client: WBApiClient,
    *,
    nm_id: int,
    target_date: str,
) -> Dict[str, Any]:
    """Top search queries for a specific product."""
    try:
        end_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"rows": [], "available": False, "api_debug": {"success": False, "reason": "invalid_date"}}

    start_dt = end_dt - timedelta(days=30)

    body = {
        "nmId": nm_id,
        "dateFrom": start_dt.isoformat(),
        "dateTo": end_dt.isoformat(),
    }

    try:
        result = client.request_json(
            endpoint=SEARCH_PRODUCT_TEXTS,
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
        query = _safe_text(item.get("query") or item.get("searchText") or item.get("text"))
        if not query:
            continue
        rows.append({
            "nm_id": nm_id,
            "query": query,
            "frequency": _safe_int(item.get("frequency") or item.get("count")),
            "position": _safe_float(item.get("position") or item.get("avgPosition")),
            "clicks": _safe_int(item.get("clicks") or item.get("openCount")),
            "orders": _safe_int(item.get("orders") or item.get("ordersCount")),
            "cart": _safe_int(item.get("cart") or item.get("cartCount")),
        })

    return {
        "rows": rows,
        "available": bool(rows),
        "api_debug": {
            "endpoint": "search_product_texts",
            "nm_id": nm_id,
            "success": result.get("success", bool(rows)),
            "rows_loaded": len(rows),
        },
    }


def load_search_product_orders(
    client: WBApiClient,
    *,
    nm_id: int,
    target_date: str,
    lookback_days: int = 7,
) -> Dict[str, Any]:
    """Orders by search queries for a specific product (daily, up to 7 days)."""
    try:
        end_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"rows": [], "available": False, "api_debug": {"success": False, "reason": "invalid_date"}}

    start_dt = end_dt - timedelta(days=lookback_days)

    body = {
        "nmId": nm_id,
        "dateFrom": start_dt.isoformat(),
        "dateTo": end_dt.isoformat(),
    }

    try:
        result = client.request_json(
            endpoint=SEARCH_PRODUCT_ORDERS,
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
        query = _safe_text(item.get("query") or item.get("searchText"))
        date_str = _safe_text(item.get("date") or item.get("dt"))[:10]
        if not query:
            continue
        rows.append({
            "nm_id": nm_id,
            "query": query,
            "date": date_str,
            "orders_count": _safe_int(item.get("orders") or item.get("ordersCount")),
            "orders_amount": _safe_float(item.get("ordersAmount") or item.get("orderSum")),
            "position": _safe_float(item.get("position") or item.get("avgPosition")),
            "clicks": _safe_int(item.get("clicks") or item.get("openCount")),
        })

    return {
        "rows": rows,
        "available": bool(rows),
        "api_debug": {
            "endpoint": "search_product_orders",
            "nm_id": nm_id,
            "success": result.get("success", bool(rows)),
            "rows_loaded": len(rows),
        },
    }


def load_search_all(
    client: WBApiClient,
    *,
    nm_ids: List[int],
    target_date: str,
) -> Dict[str, Any]:
    """Load search texts + orders for all products."""
    all_texts: List[Dict[str, Any]] = []
    all_orders: List[Dict[str, Any]] = []
    debug_entries: List[Dict[str, Any]] = []

    for nm_id in nm_ids[:50]:
        texts_result = load_search_product_texts(client, nm_id=nm_id, target_date=target_date)
        all_texts.extend(texts_result.get("rows", []))
        td = texts_result.get("api_debug", {})
        if isinstance(td, dict):
            debug_entries.append(td)

        orders_result = load_search_product_orders(client, nm_id=nm_id, target_date=target_date)
        all_orders.extend(orders_result.get("rows", []))
        od = orders_result.get("api_debug", {})
        if isinstance(od, dict):
            debug_entries.append(od)

    return {
        "texts": all_texts,
        "orders": all_orders,
        "available": bool(all_texts or all_orders),
        "api_debug": {
            "endpoint": "search_all",
            "texts_loaded": len(all_texts),
            "orders_loaded": len(all_orders),
            "nm_ids_processed": len(nm_ids[:50]),
            "details": debug_entries,
        },
    }
