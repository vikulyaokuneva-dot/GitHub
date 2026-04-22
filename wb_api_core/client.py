from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, List

import requests

STATISTICS_BASE_URL = "https://statistics-api.wildberries.ru"
FINANCE_BASE_URL = "https://finance-api.wildberries.ru"
ANALYTICS_BASE_URL = "https://seller-analytics-api.wildberries.ru"

ORDERS_PATH = "/api/v1/supplier/orders"
SALES_PATH = "/api/v1/supplier/sales"
STOCKS_PATH = "/api/v1/supplier/stocks"
FINANCE_DETAILED_PATH = "/api/finance/v1/sales-reports/detailed"
SALES_FUNNEL_PRODUCTS_PATH = "/api/analytics/v3/sales-funnel/products"


class WBApiClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = str(token or os.getenv("WB_API_TOKEN", "")).strip()
        self.statistics_base_url = os.getenv("WB_STATISTICS_BASE_URL", STATISTICS_BASE_URL).rstrip("/")
        self.finance_base_url = os.getenv("WB_FINANCE_BASE_URL", FINANCE_BASE_URL).rstrip("/")
        self.analytics_base_url = os.getenv("WB_ANALYTICS_BASE_URL", ANALYTICS_BASE_URL).rstrip("/")
        self.base_url = self.statistics_base_url
        self.timeout_seconds = max(5, int(str(os.getenv("WB_API_TIMEOUT_SECONDS", "60") or "60")))
        self.max_retries = max(1, int(str(os.getenv("WB_API_MAX_RETRIES", "5") or "5")))

    def has_token(self) -> bool:
        return bool(self.token)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def request_json(
        self,
        *,
        endpoint_name: str,
        path: str,
        params: Dict[str, Any] | None = None,
        method: str = "GET",
        json_body: Any = None,
        allow_204: bool = False,
        empty_on_204: Any = None,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        if not self.has_token():
            return {
                "endpoint": endpoint_name,
                "path": path,
                "success": False,
                "payload": None,
                "error_text": "WB_API_TOKEN not provided",
                "status_code": None,
                "attempts": 0,
                "method": str(method or "GET").strip().upper() or "GET",
                "base_url": str(base_url or self.statistics_base_url).rstrip("/"),
            }

        request_method = str(method or "GET").strip().upper() or "GET"
        resolved_base_url = str(base_url or self.statistics_base_url).rstrip("/")
        url = f"{resolved_base_url}{path}"
        last_error = ""
        last_status: int | None = None
        attempts = 0

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                response = requests.request(
                    request_method,
                    url,
                    headers=self._headers(),
                    params=params or {},
                    json=(json_body if request_method != "GET" else None),
                    timeout=self.timeout_seconds,
                )
                last_status = int(response.status_code)
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except Exception as exc:
                        last_error = f"invalid_json: {exc}"
                        break
                    return {
                        "endpoint": endpoint_name,
                        "path": path,
                        "success": True,
                        "payload": payload,
                        "error_text": "",
                        "status_code": response.status_code,
                        "attempts": attempts,
                        "method": request_method,
                        "base_url": resolved_base_url,
                    }
                if response.status_code == 204 and allow_204:
                    return {
                        "endpoint": endpoint_name,
                        "path": path,
                        "success": True,
                        "payload": empty_on_204,
                        "error_text": "",
                        "status_code": response.status_code,
                        "attempts": attempts,
                        "method": request_method,
                        "base_url": resolved_base_url,
                    }
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"{response.status_code}: {response.text[:300]}"
                    time.sleep(attempt * 1.2)
                    continue
                last_error = f"{response.status_code}: {response.text[:300]}"
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(attempt * 1.2)

        return {
            "endpoint": endpoint_name,
            "path": path,
            "success": False,
            "payload": None,
            "error_text": last_error,
            "status_code": last_status,
            "attempts": attempts,
            "method": request_method,
            "base_url": resolved_base_url,
        }

    @staticmethod
    def extract_rows(payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        for value in payload.values():
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return []
