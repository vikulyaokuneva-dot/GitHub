from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .client import ORDERS_PATH, REALIZATION_PATH, SALES_PATH, STOCKS_PATH, WBApiClient

REALIZATION_FIELDS: Sequence[str] = (
    "date",
    "nmId",
    "supplierArticle",
    "vendorCode",
    "barcode",
    "quantity",
    "retailAmount",
    "retailPriceWithDiscRub",
    "retailPrice",
    "ppvzSalesCommission",
    "deliveryRub",
    "storageFee",
    "penaltyAmount",
    "deduction",
    "ppvzForPay",
    "tax",
    "warehouseName",
    "supplierOperName",
    "supplierOperTypeName",
)


def _build_debug(
    response: Dict[str, Any],
    *,
    rows_loaded: int,
    date_from: str,
    date_to: str,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "endpoint": str(response.get("endpoint") or ""),
        "path": str(response.get("path") or ""),
        "method": str(response.get("method") or "GET"),
        "success": bool(response.get("success", False)),
        "status_code": response.get("status_code"),
        "attempts": int(response.get("attempts", 0) or 0),
        "rows_loaded": int(rows_loaded),
        "error_text": str(response.get("error_text") or ""),
        "date_from": date_from,
        "date_to": date_to,
    }
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def _extract_realization_rows(payload: Any, client: WBApiClient) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def _append(items: Any) -> None:
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    rows.append(item)

    if isinstance(payload, list):
        _append(payload)
    elif isinstance(payload, dict):
        _append(payload.get("rows"))
        _append(payload.get("details"))
        for key in ("data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                _append(value)
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    _append(item.get("rows"))
                    _append(item.get("details"))
                    _append(item.get("data"))

    if rows:
        return rows
    return client.extract_rows(payload, ("data", "items", "rows", "details"))


def load_orders(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="orders",
        path=ORDERS_PATH,
        params={"dateFrom": target_date},
        allow_204=True,
        empty_on_204=[],
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(response, rows_loaded=len(rows_raw), date_from=target_date, date_to=target_date),
    }


def load_sales(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="sales",
        path=SALES_PATH,
        params={"dateFrom": target_date},
        allow_204=True,
        empty_on_204=[],
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(response, rows_loaded=len(rows_raw), date_from=target_date, date_to=target_date),
    }


def load_stocks(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="stocks",
        path=STOCKS_PATH,
        params={"dateFrom": target_date},
        allow_204=True,
        empty_on_204=[],
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(response, rows_loaded=len(rows_raw), date_from=target_date, date_to=target_date),
    }


def load_realization(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="realization",
        path=REALIZATION_PATH,
        method="POST",
        json_body={
            "dateFrom": target_date,
            "dateTo": target_date,
            "fields": list(REALIZATION_FIELDS),
        },
        allow_204=True,
        empty_on_204={"data": []},
    )
    payload = response.get("payload", {})
    rows_raw = _extract_realization_rows(payload, client)
    payload_incompatible = bool(bool(response.get("success", False)) and payload not in ({}, [], None) and not rows_raw)
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "finance_endpoint_used": REALIZATION_PATH,
                "finance_requested_fields_count": len(REALIZATION_FIELDS),
                "finance_payload_incompatible": payload_incompatible,
            },
        ),
    }


def load_bundle(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    return {
        "orders": load_orders(client, target_date),
        "sales": load_sales(client, target_date),
        "stocks": load_stocks(client, target_date),
        "realization": load_realization(client, target_date),
    }
