from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .client import (
    FINANCE_DETAILED_PATH,
    ORDERS_PATH,
    SALES_FUNNEL_PRODUCTS_PATH,
    SALES_PATH,
    STOCKS_PATH,
    WBApiClient,
)

SALES_FUNNEL_PAGE_LIMIT = 1000
FINANCE_PAGE_LIMIT = 100000
FINANCE_FINAL_FIELDS: Sequence[str] = (
    "saleDate",
    "nmId",
    "supplierArticle",
    "vendorCode",
    "barcode",
    "srid",
    "rrdId",
    "reportId",
    "quantity",
    "retailAmount",
    "retailPriceWithDiscRub",
    "retailPrice",
    "ppvzSalesCommission",
    "deliveryRub",
    "storageFee",
    "penaltyAmount",
    "deduction",
    "acquiringFee",
    "ppvzForPay",
    "tax",
    "warehouseName",
    "docTypeName",
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
        "base_url": str(response.get("base_url") or ""),
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


def _extract_sales_funnel_rows(payload: Any, client: WBApiClient) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            products = data.get("products")
            if isinstance(products, list):
                return [row for row in products if isinstance(row, dict)]
        products = payload.get("products")
        if isinstance(products, list):
            return [row for row in products if isinstance(row, dict)]
    return client.extract_rows(payload, ("products", "items", "rows"))


def load_cabinet_commerce(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    rows_raw: List[Dict[str, Any]] = []
    pages_loaded = 0
    offset = 0
    last_page_rows_loaded = 0
    last_response: Dict[str, Any] = {
        "endpoint": "cabinet_commerce",
        "path": SALES_FUNNEL_PRODUCTS_PATH,
        "method": "POST",
        "base_url": client.analytics_base_url,
        "success": False,
        "status_code": None,
        "attempts": 0,
        "error_text": "",
    }

    while True:
        response = client.request_json(
            endpoint_name="cabinet_commerce",
            path=SALES_FUNNEL_PRODUCTS_PATH,
            method="POST",
            json_body={
                "selectedPeriod": {"start": target_date, "end": target_date},
                "nmIds": [],
                "brandNames": [],
                "subjectIds": [],
                "tagIds": [],
                "skipDeletedNm": True,
                "limit": SALES_FUNNEL_PAGE_LIMIT,
                "offset": offset,
            },
            allow_204=True,
            empty_on_204={"data": {"products": []}},
            base_url=client.analytics_base_url,
        )
        last_response = response
        if not bool(response.get("success", False)):
            break
        page_rows = _extract_sales_funnel_rows(response.get("payload", {}), client)
        last_page_rows_loaded = len(page_rows)
        rows_raw.extend(page_rows)
        pages_loaded += 1
        if last_page_rows_loaded < SALES_FUNNEL_PAGE_LIMIT:
            break
        offset += SALES_FUNNEL_PAGE_LIMIT

    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            last_response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": "cabinet_commerce_daily",
                "page_limit": SALES_FUNNEL_PAGE_LIMIT,
                "pages_loaded": pages_loaded,
                "last_offset": offset,
                "pagination_complete": bool(bool(last_response.get("success", False)) and last_page_rows_loaded < SALES_FUNNEL_PAGE_LIMIT),
            },
        ),
    }


def load_orders(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="orders",
        path=ORDERS_PATH,
        params={"dateFrom": target_date, "flag": 0},
        allow_204=True,
        empty_on_204=[],
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "flag_used": 0,
                "date_semantics": "lastChangeDate_gte_dateFrom",
            },
        ),
    }


def load_sales(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="sales",
        path=SALES_PATH,
        params={"dateFrom": target_date, "flag": 1},
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


def load_finance_final(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="finance_final",
        path=FINANCE_DETAILED_PATH,
        method="POST",
        json_body={
            "dateFrom": target_date,
            "dateTo": target_date,
            "period": "daily",
            "limit": FINANCE_PAGE_LIMIT,
            "rrdId": 0,
            "fields": list(FINANCE_FINAL_FIELDS),
        },
        allow_204=True,
        empty_on_204=[],
        base_url=client.finance_base_url,
    )
    payload = response.get("payload", [])
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
                "source_family": "finance_final_daily",
                "finance_endpoint_used": FINANCE_DETAILED_PATH,
                "finance_requested_fields_count": len(FINANCE_FINAL_FIELDS),
                "finance_requested_fields": list(FINANCE_FINAL_FIELDS),
                "finance_period": "daily",
                "finance_limit": FINANCE_PAGE_LIMIT,
                "finance_rrd_id": 0,
                "finance_pagination_truncated": len(rows_raw) >= FINANCE_PAGE_LIMIT,
                "finance_payload_incompatible": payload_incompatible,
            },
        ),
    }


def load_bundle(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    return {
        "cabinet_commerce": load_cabinet_commerce(client, target_date),
        "finance_final": load_finance_final(client, target_date),
        "orders": load_orders(client, target_date),
        "sales": load_sales(client, target_date),
        "stocks": load_stocks(client, target_date),
    }
