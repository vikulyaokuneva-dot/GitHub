from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..api.endpoints import SALES_FUNNEL_HISTORY
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


def load_funnel_history(
    client: WBApiClient,
    *,
    nm_ids: List[int],
    target_date: str,
    lookback_days: int = 7,
) -> Dict[str, Any]:
    if not nm_ids:
        return {"rows": [], "available": False, "api_debug": {"success": False, "reason": "no_nm_ids"}}

    try:
        end_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"rows": [], "available": False, "api_debug": {"success": False, "reason": "invalid_date"}}

    start_dt = end_dt - timedelta(days=lookback_days)
    period_start = start_dt.isoformat()
    period_end = end_dt.isoformat()

    body = {
        "nmIds": nm_ids,
        "period": {
            "start": period_start,
            "end": period_end,
        },
    }

    try:
        result = client.request_json(
            endpoint=SALES_FUNNEL_HISTORY,
            method="POST",
            json_body=body,
            allow_204=True,
            empty_on_204=[],
        )
    except Exception as exc:
        return {
            "rows": [],
            "available": False,
            "api_debug": {
                "success": False,
                "fail": True,
                "error_text": str(exc)[:500],
                "endpoint": "sales_funnel_history",
            },
        }

    payload = result.get("payload", result)
    if isinstance(payload, dict):
        data = payload.get("data", payload.get("rows", payload.get("items", [])))
    elif isinstance(payload, list):
        data = payload
    else:
        data = []

    if not isinstance(data, list):
        data = []

    rows: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        nm_id = _safe_int(item.get("nmId") or item.get("nm_id"))
        date_str = str(item.get("date") or item.get("dt") or "").strip()[:10]
        if not date_str or not nm_id:
            continue
        rows.append({
            "nm_id": nm_id,
            "date": date_str,
            "impressions": _safe_int(item.get("impressions") or item.get("views") or item.get("openCount")),
            "clicks": _safe_int(item.get("clicks") or item.get("open_count")),
            "cart": _safe_int(item.get("cart") or item.get("cartCount") or item.get("add_to_cart")),
            "orders": _safe_int(item.get("orders") or item.get("ordersCount") or item.get("order_count")),
            "buyouts": _safe_int(item.get("buyouts") or item.get("buyoutsCount") or item.get("buyout_count")),
            "orders_amount": _safe_float(item.get("ordersAmount") or item.get("order_sum")),
            "buyouts_amount": _safe_float(item.get("buyoutsAmount") or item.get("buyout_sum")),
        })

    api_debug = {
        "endpoint": "sales_funnel_history",
        "success": result.get("success", bool(rows)),
        "fail": not bool(rows),
        "rows_loaded": len(rows),
        "period_start": period_start,
        "period_end": period_end,
        "nm_ids_requested": len(nm_ids),
        "error_text": str(result.get("error") or result.get("error_text") or "")[:500],
        "status_code": result.get("status_code"),
    }

    return {
        "rows": rows,
        "available": bool(rows),
        "api_debug": api_debug,
    }
