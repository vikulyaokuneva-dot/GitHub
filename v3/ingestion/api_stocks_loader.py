from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..api.endpoints import STOCKS
from ..api.wb_client import WBApiClient
from ..validation.sku_normalization import normalize_sku


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return default


def _as_sku(value: Any) -> str:
    return str(normalize_sku(value) or "")


def _pick_text(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def load_stocks_from_api(client: WBApiClient, date_from: str, date_to: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint=STOCKS,
        params={"dateFrom": date_from},
        allow_204=True,
        empty_on_204=[],
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))

    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        sku = _as_sku(
            nm_id
            or row.get("nmId")
            or row.get("nm_id")
            or row.get("nmid")
            or row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("barcode")
        )
        warehouse = _pick_text(row, ("warehouseName", "warehouse", "officeName"))
        region = _pick_text(row, ("regionName", "region", "oblastOkrugName"))
        quantity_full = _as_float(row.get("quantityFull") or row.get("quantity_full"), default=0.0)
        quantity = _as_float(row.get("quantity") or row.get("qty"), default=0.0)
        in_way_to_client = _as_float(row.get("inWayToClient"), default=0.0)
        in_way_from_client = _as_float(row.get("inWayFromClient"), default=0.0)
        stock = max(quantity_full, quantity, quantity + in_way_to_client + in_way_from_client, 0.0)

        item: Dict[str, Any] = {
            "sku": sku,
            "nm_id": nm_id,
            "quantity": round(stock, 2),
            "warehouse": warehouse,
            "warehouse_name": warehouse,
            "region": region,
            "_sku_source_field": "nm_id" if sku and sku == _as_sku(nm_id) else "supplierArticle",
            "stock": round(stock, 2),
            "_raw_row_index": index,
            "_source_dataset": "stocks_api",
        }
        rows.append(item)

    api_debug = {
        "endpoint": STOCKS.name,
        "success": bool(response.get("success", False)),
        "fail": not bool(response.get("success", False)),
        "rows_loaded": len(rows),
        "date_from": date_from,
        "date_to": date_to,
        "error_text": str(response.get("error") or ""),
        "status_code": response.get("status_code"),
        "attempts": int(response.get("attempts", 0) or 0),
    }
    return {
        "rows": rows,
        "api_debug": api_debug,
    }
