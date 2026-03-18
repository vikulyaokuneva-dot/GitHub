"""Unified WB API transport foundation for v4 ingestion.

Input: endpoint descriptors + params/body.
Output: ApiCallResult (safe wrapper around HTTP response).
Does not normalize and does not compute KPI.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from .endpoints import BASE_ADVERT, BASE_ANALYTICS, BASE_STATISTICS, WBEndpoint


@dataclass(frozen=True)
class ApiCallResult:
    """Safe HTTP response envelope for loaders."""

    ok: bool
    status_code: int | None
    payload: Any
    error_code: str | None
    error_message: str | None
    attempts: int
    url: str


class WBApiClient:
    """Thin reusable WB API client.

    Provides:
    - auth header builder
    - timeout and retry skeleton
    - get_json/post_json wrappers
    - unified error shape for source statuses
    """

    def __init__(self, token: str | None = None) -> None:
        self.token = str(token or os.getenv("WB_API_TOKEN", "")).strip()
        if not self.token:
            raise ValueError("WB_API_TOKEN not provided")

        self.timeout_seconds = self._to_int(os.getenv("WB_API_TIMEOUT_SECONDS"), default=60, minimum=5)
        self.max_retries = self._to_int(os.getenv("WB_API_MAX_RETRIES"), default=4, minimum=1)

        self.statistics_url = os.getenv("WB_STATISTICS_BASE_URL", "https://statistics-api.wildberries.ru").rstrip("/")
        self.advert_url = os.getenv("WB_ADVERT_BASE_URL", "https://advert-api.wildberries.ru").rstrip("/")
        self.analytics_url = os.getenv("WB_ANALYTICS_BASE_URL", "https://seller-analytics-api.wildberries.ru").rstrip("/")

    @staticmethod
    def _to_int(value: Any, default: int, minimum: int = 0) -> int:
        try:
            parsed = int(str(value).strip())
            return max(parsed, minimum)
        except Exception:
            return default

    @staticmethod
    def _truncate_error(text: str, limit: int = 500) -> str:
        return str(text or "").strip()[:limit]

    @staticmethod
    def extract_rows(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
        """Best-effort extraction of row-like dict items from mixed payloads."""

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
                dict_rows = [row for row in value if isinstance(row, dict)]
                if dict_rows:
                    return dict_rows

        return []

    def _base_url(self, base: str) -> str:
        if base == BASE_ADVERT:
            return self.advert_url
        if base == BASE_ANALYTICS:
            return self.analytics_url
        if base == BASE_STATISTICS:
            return self.statistics_url
        return self.statistics_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def request_json(
        self,
        *,
        endpoint: WBEndpoint,
        method: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        allow_statuses: dict[int, Any] | None = None,
    ) -> ApiCallResult:
        """Perform HTTP request with retries and safe envelope output."""

        allowed = dict(allow_statuses or {})
        query = dict(params or {})
        body = dict(json_body or {})
        verb = str(method or endpoint.method or "GET").upper()
        url = f"{self._base_url(endpoint.base)}{endpoint.path}"

        retryable_statuses = {429, 500, 502, 503, 504}
        last_error_code: str | None = None
        last_error_message: str | None = None
        last_status_code: int | None = None
        attempts = 0

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                response = requests.request(
                    verb,
                    url,
                    headers=self._headers(),
                    params=query,
                    json=body if verb != "GET" else None,
                    timeout=self.timeout_seconds,
                )
                last_status_code = int(response.status_code)

                if response.status_code in allowed:
                    return ApiCallResult(
                        ok=True,
                        status_code=last_status_code,
                        payload=allowed[response.status_code],
                        error_code=None,
                        error_message=None,
                        attempts=attempts,
                        url=url,
                    )

                if 200 <= response.status_code < 300:
                    try:
                        payload = response.json()
                    except Exception as exc:
                        return ApiCallResult(
                            ok=False,
                            status_code=last_status_code,
                            payload=None,
                            error_code="invalid_json",
                            error_message=self._truncate_error(str(exc)),
                            attempts=attempts,
                            url=url,
                        )

                    return ApiCallResult(
                        ok=True,
                        status_code=last_status_code,
                        payload=payload,
                        error_code=None,
                        error_message=None,
                        attempts=attempts,
                        url=url,
                    )

                last_error_code = f"http_{response.status_code}"
                last_error_message = self._truncate_error(response.text)

                if response.status_code in retryable_statuses and attempt < self.max_retries:
                    time.sleep(1.2 * attempt)
                    continue

                break
            except requests.RequestException as exc:
                last_error_code = "request_exception"
                last_error_message = self._truncate_error(str(exc))
                if attempt < self.max_retries:
                    time.sleep(1.2 * attempt)
                    continue
                break
            except Exception as exc:  # pragma: no cover - safety fallback
                last_error_code = "unexpected_exception"
                last_error_message = self._truncate_error(str(exc))
                break

        return ApiCallResult(
            ok=False,
            status_code=last_status_code,
            payload=None,
            error_code=last_error_code or "request_failed",
            error_message=last_error_message or "unknown request failure",
            attempts=attempts,
            url=url,
        )

    def get_json(
        self,
        endpoint: WBEndpoint,
        *,
        params: dict[str, Any] | None = None,
        allow_statuses: dict[int, Any] | None = None,
    ) -> ApiCallResult:
        return self.request_json(
            endpoint=endpoint,
            method="GET",
            params=params,
            allow_statuses=allow_statuses,
        )

    def post_json(
        self,
        endpoint: WBEndpoint,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_statuses: dict[int, Any] | None = None,
    ) -> ApiCallResult:
        return self.request_json(
            endpoint=endpoint,
            method="POST",
            params=params,
            json_body=json_body,
            allow_statuses=allow_statuses,
        )
