"""Read-only binding of the target ingestion port to the existing WB client."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping


class LegacyWBApiSalesFunnelTransport:
    """Use root ``wb_api_core.WBApiClient`` without importing it into domain packages."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def fetch_sales_funnel_products(self, *, operational_date: date) -> Mapping[str, Any]:
        from wb_api_core.client import SALES_FUNNEL_PRODUCTS_PATH  # type: ignore[import-not-found]

        response = self._client.request_json(
            endpoint_name="sales_funnel_products",
            path=SALES_FUNNEL_PRODUCTS_PATH,
            method="POST",
            json_body={
                "selectedPeriod": {"start": operational_date.isoformat(), "end": operational_date.isoformat()},
                "nmIds": [],
                "brandNames": [],
                "subjectIds": [],
                "tagIds": [],
                "skipDeletedNm": True,
                "limit": 1000,
                "offset": 0,
            },
            base_url=self._client.analytics_base_url,
        )
        if not bool(response.get("success", False)):
            status = response.get("status_code")
            raise RuntimeError(f"sales_funnel_products WB request failed with status {status}")
        payload = response.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("sales_funnel_products response must be a JSON object")
        return payload


class LegacyWBApiOperationalTransport:
    """Read-only root-client binding that retains the exact JSON response bytes."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def fetch_orders(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        from wb_api_core.client import ORDERS_PATH

        return self._request_array(
            endpoint_name="orders",
            path=ORDERS_PATH,
            params={"dateFrom": operational_date.isoformat(), "flag": 0},
        )

    def fetch_sales(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        from wb_api_core.client import SALES_PATH

        return self._request_array(
            endpoint_name="sales",
            path=SALES_PATH,
            params={"dateFrom": operational_date.isoformat(), "flag": 1},
        )

    def _request_array(self, *, endpoint_name: str, path: str, params: dict[str, Any]) -> tuple[list[dict[str, Any]], bytes]:
        response = self._client.request_json(endpoint_name=endpoint_name, path=path, params=params)
        if not bool(response.get("success", False)):
            raise RuntimeError(f"{endpoint_name} WB request failed with status {response.get('status_code')}")
        payload = response.get("payload")
        raw_bytes = response.get("payload_bytes")
        if not isinstance(payload, list) or raw_bytes is None or not all(isinstance(item, dict) for item in payload):
            raise ValueError(f"{endpoint_name} response must be a JSON array of objects")
        return payload, raw_bytes


class LegacyWBApiFinanceDetailTransport:
    """Read-only binding to the existing finance-detail endpoint."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def fetch_finance_detail(self, *, operational_date: date) -> tuple[dict[str, Any] | list[Any], bytes]:
        from wb_api_core.client import FINANCE_DETAILED_PATH

        response = self._client.request_json(
            endpoint_name="finance_detail",
            path=FINANCE_DETAILED_PATH,
            method="POST",
            json_body={
                "dateFrom": operational_date.isoformat(),
                "dateTo": operational_date.isoformat(),
                "period": "daily",
                "limit": 100000,
                "rrdId": 0,
            },
            allow_204=True,
            empty_on_204={"data": []},
            base_url=self._client.finance_base_url,
            retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
        )
        if not bool(response.get("success", False)):
            raise RuntimeError(f"finance_detail WB request failed with status {response.get('status_code')}")
        payload = response.get("payload")
        raw_bytes = response.get("payload_bytes")
        if not isinstance(payload, (dict, list)) or not isinstance(raw_bytes, bytes):
            raise ValueError("finance_detail response must be a JSON object or array with retained bytes")
        return payload, raw_bytes


_LEGACY_ADVERTISING_FIELD_MAP: dict[str, str] = {
    "ads_spend": "sum",
    "nm_id": "nmId",
}


def map_legacy_advertising_row(row: dict[str, Any]) -> dict[str, Any]:
    """Rename legacy advertising aggregate fields to the AD2 contract.

    Only fields present in the source row are renamed (``ads_spend`` ->
    ``sum``, ``nm_id`` -> ``nmId``); all other fields are preserved verbatim.
    No ``advertId`` or ``attributionScope`` is invented: the legacy aggregate
    carries no campaign identifier, and the AD2 normalizer classifies rows
    with a concrete ``nmId`` (and no scope field) as direct-SKU spend while
    rows without one fall back to UNKNOWN. Aggregation semantics of the
    source (per-SKU daily totals) stay unchanged by this rename.
    """

    mapped = dict(row)
    for legacy_key, ad2_key in _LEGACY_ADVERTISING_FIELD_MAP.items():
        if legacy_key in mapped:
            mapped[ad2_key] = mapped.pop(legacy_key)
    return mapped


class LegacyWBApiLoadersTransport:
    """Read-only binding of the daily ingestion transport to existing ``wb_api_core`` loaders.

    Each method delegates to the same legacy loader function with the same
    arguments the daily ingestion previously called directly, so the persisted
    raw payload semantics stay unchanged.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def load_orders(self, *, operational_date: date) -> dict[str, Any]:
        from wb_api_core.loaders import load_orders  # type: ignore[import-not-found]

        return load_orders(self._client, operational_date.isoformat())

    def load_sales(self, *, operational_date: date) -> dict[str, Any]:
        from wb_api_core.loaders import load_sales  # type: ignore[import-not-found]

        return load_sales(self._client, operational_date.isoformat())

    def load_stocks(self, *, operational_date: date) -> dict[str, Any]:
        from wb_api_core.loaders import load_stocks  # type: ignore[import-not-found]

        return load_stocks(self._client, operational_date.isoformat())

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, Any]:
        """Return the raw sales-funnel WB response instead of legacy loader rows.

        The AD2 funnel normalizer contract expects the untouched WB response
        shape (``data.products[]``), so the daily ingestion must persist the
        raw funnel payload, not the legacy aggregated rows.
        """

        from wb_api_core.client import SALES_FUNNEL_PRODUCTS_PATH  # type: ignore[import-not-found]

        response = self._client.request_json(
            endpoint_name="sales_funnel_products",
            path=SALES_FUNNEL_PRODUCTS_PATH,
            method="POST",
            json_body={
                "selectedPeriod": {"start": operational_date.isoformat(), "end": operational_date.isoformat()},
                "nmIds": [],
                "brandNames": [],
                "subjectIds": [],
                "tagIds": [],
                "skipDeletedNm": True,
                "limit": 1000,
                "offset": 0,
            },
            base_url=self._client.analytics_base_url,
            retry_policy={
                "retryable_statuses": (429, 500, 502, 503, 504),
                "max_attempts": 6,
                "base_delay_seconds": 10.0,
                "cap_delay_seconds": 20.0,
                "jitter_ratio": 0.15,
                "max_delay_seconds": 30.0,
            },
        )
        if not bool(response.get("success", False)):
            raise RuntimeError(f"sales_funnel_products WB request failed with status {response.get('status_code')}")
        payload = response.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("sales_funnel_products response must be a JSON object")
        return {"payload": payload}

    def load_ads(self, *, operational_date: date) -> dict[str, Any]:
        from wb_api_core.loaders import load_ads  # type: ignore[import-not-found]

        result = load_ads(self._client, operational_date.isoformat())
        rows = result.get("rows_raw")
        if isinstance(rows, list):
            result = dict(result)
            result["rows_raw"] = [map_legacy_advertising_row(row) for row in rows if isinstance(row, dict)]
        return result
