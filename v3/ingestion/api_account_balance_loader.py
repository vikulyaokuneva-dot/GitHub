from __future__ import annotations

from typing import Any, Dict

from ..api.endpoints import ACCOUNT_BALANCE
from ..api.wb_client import WBApiClient


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_account_balance(client: WBApiClient) -> Dict[str, Any]:
    """Load account balance for cross-checking seller_payout."""
    try:
        result = client.request_json(
            endpoint=ACCOUNT_BALANCE,
            allow_204=True,
            empty_on_204={},
        )
    except Exception as exc:
        return {"available": False, "api_debug": {"success": False, "error_text": str(exc)[:500]}}

    payload = result.get("payload", result)
    if not isinstance(payload, dict):
        payload = {}

    balance = _safe_float(payload.get("balance"))
    awaiting_payment = _safe_float(payload.get("awaitingPayment") or payload.get("awaiting_payment"))
    awaiting_placement = _safe_float(payload.get("awaitingPlacement") or payload.get("awaiting_placement"))

    return {
        "available": bool(payload),
        "balance": round(balance, 2),
        "awaiting_payment": round(awaiting_payment, 2),
        "awaiting_placement": round(awaiting_placement, 2),
        "api_debug": {
            "endpoint": "account_balance",
            "success": result.get("success", bool(payload)),
            "rows_loaded": 1 if payload else 0,
        },
    }
