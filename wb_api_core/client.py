from __future__ import annotations

import os
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List

import requests

from .token_resolver import resolve_wb_api_token

STATISTICS_BASE_URL = "https://statistics-api.wildberries.ru"
FINANCE_BASE_URL = "https://finance-api.wildberries.ru"
ANALYTICS_BASE_URL = "https://seller-analytics-api.wildberries.ru"
ADVERT_BASE_URL = "https://advert-api.wildberries.ru"
PRICES_BASE_URL = "https://discounts-prices-api.wildberries.ru"
MARKETPLACE_BASE_URL = "https://marketplace-api.wildberries.ru"

ORDERS_PATH = "/api/v1/supplier/orders"
SALES_PATH = "/api/v1/supplier/sales"
STOCKS_WB_WAREHOUSES_PATH = "/api/analytics/v1/stocks-report/wb-warehouses"
FINANCE_DETAILED_PATH = "/api/finance/v1/sales-reports/detailed"
SALES_FUNNEL_PRODUCTS_PATH = "/api/analytics/v3/sales-funnel/products"
ADVERTS_PATH = "/api/advert/v2/adverts"
ADVERT_STATS_PATH = "/adv/v3/fullstats"
SEARCH_REPORT_GROUPS_PATH = "/api/v2/search-report/table/groups"
SEARCH_REPORT_DETAILS_PATH = "/api/v2/search-report/table/details"
GOODS_PRICES_PATH = "/api/v2/list/goods/filter"
FBS_NEW_ORDERS_PATH = "/api/v3/orders/new"
FBS_ORDERS_PATH = "/api/v3/orders"
DEFAULT_RATE_LIMIT_RETRY_DELAY_CAP_SECONDS = 30.0
DEFAULT_GLOBAL_REQUEST_BUDGET = 25


class WBApiClient:
    def __init__(self, token: str | None = None) -> None:
        self.token, self.token_env_name_used = resolve_wb_api_token(token)
        self.statistics_base_url = os.getenv("WB_STATISTICS_BASE_URL", STATISTICS_BASE_URL).rstrip("/")
        self.finance_base_url = os.getenv("WB_FINANCE_BASE_URL", FINANCE_BASE_URL).rstrip("/")
        self.analytics_base_url = os.getenv("WB_ANALYTICS_BASE_URL", ANALYTICS_BASE_URL).rstrip("/")
        self.advert_base_url = os.getenv("WB_ADVERT_BASE_URL", ADVERT_BASE_URL).rstrip("/")
        self.prices_base_url = os.getenv("WB_PRICES_BASE_URL", PRICES_BASE_URL).rstrip("/")
        self.marketplace_base_url = os.getenv("WB_MARKETPLACE_BASE_URL", MARKETPLACE_BASE_URL).rstrip("/")
        self.base_url = self.statistics_base_url
        self.timeout_seconds = max(5, int(str(os.getenv("WB_API_TIMEOUT_SECONDS", "60") or "60")))
        self.max_retries = max(1, int(str(os.getenv("WB_API_MAX_RETRIES", "5") or "5")))
        self.global_request_budget = max(1, int(str(os.getenv("WB_API_GLOBAL_BUDGET", str(DEFAULT_GLOBAL_REQUEST_BUDGET)) or str(DEFAULT_GLOBAL_REQUEST_BUDGET))))
        self._global_request_count = 0

    def has_token(self) -> bool:
        return bool(self.token)

    def has_request_budget(self) -> bool:
        return self._global_request_count < self.global_request_budget

    def _increment_request_count(self) -> None:
        self._global_request_count += 1

    def request_count(self) -> int:
        return self._global_request_count

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
        try:
            max_delay_seconds = max(0.0, float(policy.get("max_delay_seconds", 0.0) or 0.0))
        except Exception:
            max_delay_seconds = 0.0
        try:
            max_delay = max(0.0, float(policy.get("max_delay", 0.0) or 0.0))
        except Exception:
            max_delay = 0.0
        return {
            "retryable_statuses": retryable,
            "max_attempts": max_attempts,
            "base_delay_seconds": base_delay_seconds,
            "cap_delay_seconds": cap_delay_seconds,
            "jitter_ratio": jitter_ratio,
            "max_retry_window_seconds": max_retry_window_seconds,
            "max_delay_seconds": max_delay_seconds,
            "max_delay": max_delay,
        }

    @staticmethod
    def _response_header(response: requests.Response, header_name: str) -> str:
        try:
            value = response.headers.get(header_name)
        except Exception:
            value = None
        if value is None:
            try:
                for key, candidate in response.headers.items():
                    if str(key or "").strip().lower() == header_name.lower():
                        value = candidate
                        break
            except Exception:
                value = None
        return str(value or "").strip()

    @staticmethod
    def _parse_delay_header_seconds(value: Any, *, now_epoch: float, reset_header: bool = False) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            numeric = float(text)
            if reset_header:
                if numeric > 1_000_000_000_000:
                    return max(0.0, numeric / 1000.0 - now_epoch)
                if numeric > 1_000_000_000:
                    return max(0.0, numeric - now_epoch)
            return max(0.0, numeric)
        except Exception:
            pass
        try:
            parsed = parsedate_to_datetime(text)
            return max(0.0, parsed.timestamp() - now_epoch)
        except Exception:
            return None

    @classmethod
    def _parse_rate_limit_headers(cls, response: requests.Response) -> Dict[str, Any]:
        try:
            now_epoch = float(time.time())
        except Exception:
            now_epoch = 0.0
        retry_after = cls._response_header(response, "Retry-After")
        x_ratelimit_retry = cls._response_header(response, "X-Ratelimit-Retry")
        x_ratelimit_reset = cls._response_header(response, "X-Ratelimit-Reset")
        return {
            "retry_after": retry_after,
            "retry_after_seconds": cls._parse_delay_header_seconds(retry_after, now_epoch=now_epoch),
            "x_ratelimit_retry": x_ratelimit_retry,
            "x_ratelimit_retry_seconds": cls._parse_delay_header_seconds(x_ratelimit_retry, now_epoch=now_epoch),
            "x_ratelimit_reset": x_ratelimit_reset,
            "x_ratelimit_reset_seconds": cls._parse_delay_header_seconds(
                x_ratelimit_reset,
                now_epoch=now_epoch,
                reset_header=True,
            ),
            "x_ratelimit_remaining": cls._response_header(response, "X-Ratelimit-Remaining"),
        }

    @staticmethod
    def _has_rate_limit_details(details: Dict[str, Any]) -> bool:
        return any(
            bool(str(details.get(key) or "").strip())
            for key in ("retry_after", "x_ratelimit_retry", "x_ratelimit_reset", "x_ratelimit_remaining")
        )

    @staticmethod
    def _retry_delay_cap_seconds(retry_policy: Dict[str, Any]) -> float:
        for key in ("max_delay_seconds", "max_delay"):
            try:
                cap_delay = float(retry_policy.get(key, 0.0) or 0.0)
            except Exception:
                cap_delay = 0.0
            if cap_delay > 0:
                return cap_delay
        return DEFAULT_RATE_LIMIT_RETRY_DELAY_CAP_SECONDS

    @classmethod
    def _header_retry_delay_seconds(cls, details: Dict[str, Any], retry_policy: Dict[str, Any]) -> float | None:
        for key in ("retry_after_seconds", "x_ratelimit_retry_seconds", "x_ratelimit_reset_seconds"):
            value = details.get(key)
            if value is None:
                continue
            try:
                delay = max(0.0, float(value))
            except Exception:
                continue
            delay = min(delay, cls._retry_delay_cap_seconds(retry_policy))
            return round(delay, 2)
        return None

    @staticmethod
    def _rate_limit_response_fields(details: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "retry_after": str(details.get("retry_after") or ""),
            "x_ratelimit_retry": str(details.get("x_ratelimit_retry") or ""),
            "x_ratelimit_reset": str(details.get("x_ratelimit_reset") or ""),
            "x_ratelimit_remaining": str(details.get("x_ratelimit_remaining") or ""),
            "rate_limit_delay_seconds": details.get("rate_limit_delay_seconds"),
        }

    @classmethod
    def _status_error_text(cls, response: requests.Response, rate_limit_details: Dict[str, Any]) -> str:
        base = f"{response.status_code}: {response.text[:300]}"
        if not cls._has_rate_limit_details(rate_limit_details):
            return base
        parts = []
        for key in ("retry_after", "x_ratelimit_retry", "x_ratelimit_reset", "x_ratelimit_remaining"):
            value = str(rate_limit_details.get(key) or "").strip()
            if value:
                parts.append(f"{key}={value}")
        return f"{base}; rate_limit_headers: {', '.join(parts)}" if parts else base

    @classmethod
    def _retry_after_seconds(cls, response: requests.Response) -> float:
        details = cls._parse_rate_limit_headers(response)
        try:
            return max(0.0, float(details.get("retry_after_seconds") or 0.0))
        except Exception:
            return 0.0

    @staticmethod
    def _retry_details_with_delay(details: Dict[str, Any], delay_seconds: float | None) -> Dict[str, Any]:
        updated = dict(details)
        updated["rate_limit_delay_seconds"] = delay_seconds
        return updated

    @classmethod
    def _compute_default_retry_delay_seconds(
        cls,
        *,
        attempt: int,
        retry_policy: Dict[str, Any],
        rate_limit_details: Dict[str, Any],
    ) -> float:
        header_delay = cls._header_retry_delay_seconds(rate_limit_details, retry_policy)
        if header_delay is not None:
            return header_delay
        return round(float(attempt) * 1.2, 2)

    @classmethod
    def _compute_exception_retry_delay_seconds(
        cls,
        *,
        attempt: int,
        use_custom_retry_policy: bool,
    ) -> float:
        return round(float(attempt) * 1.2, 2) if not use_custom_retry_policy else min(5.0, float(attempt))

    @classmethod
    def _compute_header_or_backoff_delay_seconds(
        cls,
        *,
        retry_number: int,
        response: requests.Response,
        retry_policy: Dict[str, Any],
        rate_limit_details: Dict[str, Any] | None = None,
    ) -> float:
        details = dict(rate_limit_details or cls._parse_rate_limit_headers(response))
        header_delay = cls._header_retry_delay_seconds(details, retry_policy)
        if header_delay is not None:
            return header_delay
        try:
            base_delay = float(retry_policy.get("base_delay_seconds", 0.0) or 0.0)
        except Exception:
            base_delay = 0.0
        try:
            cap_delay = float(retry_policy.get("cap_delay_seconds", base_delay) or base_delay)
        except Exception:
            cap_delay = base_delay
        jitter_ratio = float(retry_policy.get("jitter_ratio", 0.0) or 0.0)
        exponential_delay = min(cap_delay, base_delay * (2 ** max(retry_number - 1, 0)))
        jitter = random.uniform(0.0, exponential_delay * jitter_ratio) if exponential_delay > 0 and jitter_ratio > 0 else 0.0
        return round(exponential_delay + jitter, 2)

    def _compute_retry_delay_seconds(
        self,
        *,
        retry_number: int,
        response: requests.Response,
        retry_policy: Dict[str, Any],
        rate_limit_details: Dict[str, Any] | None = None,
    ) -> float:
        return self._compute_header_or_backoff_delay_seconds(
            retry_number=retry_number,
            response=response,
            retry_policy=retry_policy,
            rate_limit_details=rate_limit_details,
        )

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

        if not self.has_request_budget():
            return {
                "endpoint": endpoint_name,
                "path": path,
                "success": False,
                "payload": None,
                "error_text": f"global request budget exhausted ({self.global_request_budget})",
                "status_code": None,
                "attempts": 0,
                "retry_count": 0,
                "retry_delays": [],
                "final_failure_reason": f"global request budget exhausted ({self.global_request_budget})",
                "method": str(method or "GET").strip().upper() or "GET",
                "base_url": str(base_url or self.statistics_base_url).rstrip("/"),
                "token_present": True,
                "token_env_name_used": self.token_env_name_used,
                "global_budget_exhausted": True,
                "global_request_count": self._global_request_count,
            }

        self._increment_request_count()

        request_method = str(method or "GET").strip().upper() or "GET"
        resolved_base_url = str(base_url or self.statistics_base_url).rstrip("/")
        url = f"{resolved_base_url}{path}"
        last_error = ""
        last_status: int | None = None
        attempts = 0
        retry_delays: List[float] = []
        total_retry_delay_seconds = 0.0
        last_rate_limit_details: Dict[str, Any] = {}
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
                rate_limit_details = self._parse_rate_limit_headers(response)
                if response.status_code == 429 or self._has_rate_limit_details(rate_limit_details):
                    last_rate_limit_details = rate_limit_details
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
                        **self._rate_limit_response_fields(last_rate_limit_details),
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
                        **self._rate_limit_response_fields(last_rate_limit_details),
                    }
                if response.status_code in normalized_retry_policy.get("retryable_statuses", set()) and attempt < max_attempts:
                    last_error = self._status_error_text(response, rate_limit_details)
                    if use_custom_retry_policy:
                        delay_seconds = self._compute_retry_delay_seconds(
                            retry_number=len(retry_delays) + 1,
                            response=response,
                            retry_policy=normalized_retry_policy,
                            rate_limit_details=rate_limit_details,
                        )
                        max_retry_window_seconds = float(normalized_retry_policy.get("max_retry_window_seconds", 0.0) or 0.0)
                        if max_retry_window_seconds > 0 and total_retry_delay_seconds + delay_seconds > max_retry_window_seconds:
                            last_error = f"retry_window_exhausted: {last_error}"
                            break
                    else:
                        delay_seconds = self._compute_default_retry_delay_seconds(
                            attempt=attempt,
                            retry_policy=normalized_retry_policy,
                            rate_limit_details=rate_limit_details,
                        )
                    last_rate_limit_details = self._retry_details_with_delay(rate_limit_details, delay_seconds)
                    retry_delays.append(delay_seconds)
                    total_retry_delay_seconds += delay_seconds
                    time.sleep(delay_seconds)
                    continue
                last_error = self._status_error_text(response, rate_limit_details)
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt >= max_attempts:
                    break
                delay_seconds = self._compute_exception_retry_delay_seconds(
                    attempt=attempt,
                    use_custom_retry_policy=use_custom_retry_policy,
                )
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
            **self._rate_limit_response_fields(last_rate_limit_details),
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
