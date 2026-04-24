from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, Iterable, List

import requests

from .token_resolver import resolve_wb_api_token

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
        self.token, self.token_env_name_used = resolve_wb_api_token(token)
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

    @staticmethod
    def _normalize_retry_policy(retry_policy: Dict[str, Any] | None) -> Dict[str, Any]:
        policy = dict(retry_policy or {})
        retryable_statuses = policy.get("retryable_statuses", (429, 500, 502, 503, 504))
        try:
            retryable = {int(item) for item in list(retryable_statuses or ())}
        except Exception:
            retryable = {429, 500, 502, 503, 504}
        try:
            max_attempts = max(1, int(policy.get("max_attempts", 1) or 1))
        except Exception:
            max_attempts = 1
        try:
            base_delay_seconds = max(0.0, float(policy.get("base_delay_seconds", 0.0) or 0.0))
        except Exception:
            base_delay_seconds = 0.0
        try:
            cap_delay_seconds = max(base_delay_seconds, float(policy.get("cap_delay_seconds", base_delay_seconds) or base_delay_seconds))
        except Exception:
            cap_delay_seconds = base_delay_seconds
        try:
            jitter_ratio = min(max(float(policy.get("jitter_ratio", 0.0) or 0.0), 0.0), 1.0)
        except Exception:
            jitter_ratio = 0.0
        try:
            max_retry_window_seconds = max(0.0, float(policy.get("max_retry_window_seconds", 0.0) or 0.0))
        except Exception:
            max_retry_window_seconds = 0.0
        return {
            "retryable_statuses": retryable,
            "max_attempts": max_attempts,
            "base_delay_seconds": base_delay_seconds,
            "cap_delay_seconds": cap_delay_seconds,
            "jitter_ratio": jitter_ratio,
            "max_retry_window_seconds": max_retry_window_seconds,
        }

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> float:
        try:
            retry_after = str(response.headers.get("Retry-After") or "").strip()
        except Exception:
            retry_after = ""
        if not retry_after:
            return 0.0
        try:
            return max(0.0, float(retry_after))
        except Exception:
            return 0.0

    def _compute_retry_delay_seconds(
        self,
        *,
        retry_number: int,
        response: requests.Response,
        retry_policy: Dict[str, Any],
    ) -> float:
        base_delay = float(retry_policy.get("base_delay_seconds", 0.0) or 0.0)
        cap_delay = float(retry_policy.get("cap_delay_seconds", base_delay) or base_delay)
        jitter_ratio = float(retry_policy.get("jitter_ratio", 0.0) or 0.0)
        exponential_delay = min(cap_delay, base_delay * (2 ** max(retry_number - 1, 0)))
        jitter = random.uniform(0.0, exponential_delay * jitter_ratio) if exponential_delay > 0 and jitter_ratio > 0 else 0.0
        retry_after = self._retry_after_seconds(response)
        delay = max(exponential_delay + jitter, retry_after)
        return round(delay, 2)

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
        retry_policy: Dict[str, Any] | None = None,
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
                "retry_count": 0,
                "retry_delays": [],
                "final_failure_reason": "WB_API_TOKEN not provided",
                "method": str(method or "GET").strip().upper() or "GET",
                "base_url": str(base_url or self.statistics_base_url).rstrip("/"),
                "token_present": False,
                "token_env_name_used": self.token_env_name_used,
            }

        request_method = str(method or "GET").strip().upper() or "GET"
        resolved_base_url = str(base_url or self.statistics_base_url).rstrip("/")
        url = f"{resolved_base_url}{path}"
        last_error = ""
        last_status: int | None = None
        attempts = 0
        retry_delays: List[float] = []
        total_retry_delay_seconds = 0.0
        use_custom_retry_policy = isinstance(retry_policy, dict)
        normalized_retry_policy = self._normalize_retry_policy(
            retry_policy if use_custom_retry_policy else {"retryable_statuses": (429, 500, 502, 503, 504), "max_attempts": self.max_retries}
        )
        max_attempts = int(normalized_retry_policy.get("max_attempts", 1) or 1)

        for attempt in range(1, max_attempts + 1):
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
                        "retry_count": len(retry_delays),
                        "retry_delays": list(retry_delays),
                        "final_failure_reason": "",
                        "method": request_method,
                        "base_url": resolved_base_url,
                        "token_present": True,
                        "token_env_name_used": self.token_env_name_used,
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
                        "retry_count": len(retry_delays),
                        "retry_delays": list(retry_delays),
                        "final_failure_reason": "",
                        "method": request_method,
                        "base_url": resolved_base_url,
                        "token_present": True,
                        "token_env_name_used": self.token_env_name_used,
                    }
                if response.status_code in normalized_retry_policy.get("retryable_statuses", set()) and attempt < max_attempts:
                    last_error = f"{response.status_code}: {response.text[:300]}"
                    if use_custom_retry_policy:
                        delay_seconds = self._compute_retry_delay_seconds(
                            retry_number=len(retry_delays) + 1,
                            response=response,
                            retry_policy=normalized_retry_policy,
                        )
                        max_retry_window_seconds = float(normalized_retry_policy.get("max_retry_window_seconds", 0.0) or 0.0)
                        if max_retry_window_seconds > 0 and total_retry_delay_seconds + delay_seconds > max_retry_window_seconds:
                            last_error = f"retry_window_exhausted: {last_error}"
                            break
                    else:
                        delay_seconds = round(float(attempt) * 1.2, 2)
                    retry_delays.append(delay_seconds)
                    total_retry_delay_seconds += delay_seconds
                    time.sleep(delay_seconds)
                    continue
                last_error = f"{response.status_code}: {response.text[:300]}"
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt >= max_attempts:
                    break
                delay_seconds = round(float(attempt) * 1.2, 2) if not use_custom_retry_policy else min(5.0, float(attempt))
                retry_delays.append(round(delay_seconds, 2))
                total_retry_delay_seconds += delay_seconds
                time.sleep(delay_seconds)

        return {
            "endpoint": endpoint_name,
            "path": path,
            "success": False,
            "payload": None,
            "error_text": last_error,
            "status_code": last_status,
            "attempts": attempts,
            "retry_count": len(retry_delays),
            "retry_delays": list(retry_delays),
            "final_failure_reason": last_error,
            "method": request_method,
            "base_url": resolved_base_url,
            "token_present": True,
            "token_env_name_used": self.token_env_name_used,
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
