from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..api.endpoints import SALES_FUNNEL_HISTORY
from ..api.wb_client import WBApiClient

_BATCH_SIZE = 20


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


def _parse_history_response(data: Any) -> List[Dict[str, Any]]:
    """Parse WB funnel history response: [{product: {nmId}, history: [{date, openCount, ...}]}]."""
    rows: List[Dict[str, Any]] = []
    if not isinstance(data, list):
        return rows

    for product_block in data:
        if not isinstance(product_block, dict):
            continue
        product = product_block.get("product") if isinstance(product_block.get("product"), dict) else {}
        nm_id = _safe_int(
            product.get("nmId")
            or product.get("nm_id")
            or product_block.get("nmId")
            or product_block.get("nm_id")
        )
        if not nm_id:
            continue

        history = product_block.get("history") or product_block.get("days") or []
        if not isinstance(history, list):
            continue

        for item in history:
            if not isinstance(item, dict):
                continue
            date_str = str(item.get("date") or item.get("dt") or "").strip()[:10]
            if not date_str:
                continue
            rows.append({
                "nm_id": nm_id,
                "date": date_str,
                "card_opens": _safe_int(item.get("openCount") or item.get("open_count")),
                "cart": _safe_int(item.get("cartCount") or item.get("cart_count")),
                "orders": _safe_int(item.get("orderCount") or item.get("order_count")),
                "buyouts": _safe_int(item.get("buyoutCount") or item.get("buyout_count")),
            })

    return rows


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

    all_rows: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i in range(0, len(nm_ids), _BATCH_SIZE):
        batch = nm_ids[i : i + _BATCH_SIZE]
        body = {
            "selectedPeriod": {
                "start": period_start,
                "end": period_end,
            },
            "nmIds": batch,
            "skipDeletedNm": True,
            "aggregationLevel": "day",
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
            errors.append(str(exc)[:200])
            continue

        payload = result.get("payload", result)
        if isinstance(payload, dict):
            data = payload.get("data", payload.get("rows", payload.get("items", [])))
        elif isinstance(payload, list):
            data = payload
        else:
            data = []

        all_rows.extend(_parse_history_response(data))

    api_debug = {
        "endpoint": "sales_funnel_history",
        "success": bool(all_rows),
        "fail": not bool(all_rows),
        "rows_loaded": len(all_rows),
        "period_start": period_start,
        "period_end": period_end,
        "nm_ids_requested": len(nm_ids),
        "batches": (len(nm_ids) + _BATCH_SIZE - 1) // _BATCH_SIZE,
        "error_text": "; ".join(errors)[:500] if errors else "",
    }

    return {
        "rows": all_rows,
        "available": bool(all_rows),
        "api_debug": api_debug,
    }
