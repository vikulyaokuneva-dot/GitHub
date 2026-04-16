from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, List

import requests

from .endpoints import BASE_ADVERT, BASE_STATISTICS, WBEndpoint


class WBApiClient:
    def __init__(self, token: str | None = None):
        self.token = str(token or os.getenv("WB_API_TOKEN", "")).strip()
        if not self.token:
            raise ValueError("WB_API_TOKEN not provided")

        self.timeout_seconds = int(str(os.getenv("WB_API_TIMEOUT_SECONDS", "60") or "60"))
        self.max_retries = int(str(os.getenv("WB_API_MAX_RETRIES", "5") or "5"))

        self.statistics_url = os.getenv("WB_STATISTICS_BASE_URL", "https://statistics-api.wildberries.ru").rstrip("/")
        self.advert_url = os.getenv("WB_ADVERT_BASE_URL", "https://advert-api.wildberries.ru").rstrip("/")

    @staticmethod
    def _extract_rows(payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
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

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def _base_url(self, base_name: str) -> str:
        if base_name == BASE_ADVERT:
            return self.advert_url
        return self.statistics_url

    def request_json(
        self,
        endpoint: WBEndpoint,
        params: Dict[str, Any] | None = None,
        method: str = "GET",
        json_body: Any = None,
        *,
        allow_204: bool = False,
        empty_on_204: Any = None,
        allow_403: bool = False,
        empty_on_403: Any = None,
    ) -> Dict[str, Any]:
        request_params = params or {}
        max_retries = max(1, self._to_int(self.max_retries, 5))
        timeout_seconds = max(5, self._to_int(self.timeout_seconds, 60))
        request_method = str(method or "GET").strip().upper() or "GET"
        url = f"{self._base_url(endpoint.base)}{endpoint.path}"

        last_error = ""
        last_status: int | None = None
        attempts = 0
        for attempt in range(1, max_retries + 1):
            attempts = attempt
            try:
                request_payload = json_body if request_method != "GET" else None
                response = requests.request(
                    request_method,
                    url,
                    headers=self._headers(),
                    params=request_params,
                    json=request_payload,
                    timeout=timeout_seconds,
                )
                last_status = int(response.status_code)
                print(
                    f"[wb_api] endpoint={endpoint.name} method={request_method} "
                    f"attempt={attempt} status={response.status_code}"
                )
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except Exception as exc:
                        last_error = f"invalid_json: {exc}"
                        break
                    return {
                        "success": True,
                        "payload": payload,
                        "error": "",
                        "status_code": response.status_code,
                        "attempts": attempts,
                    }
                if response.status_code == 204 and allow_204:
                    return {
                        "success": True,
                        "payload": empty_on_204,
                        "error": "",
                        "status_code": response.status_code,
                        "attempts": attempts,
                    }
                if response.status_code == 403 and allow_403:
                    return {
                        "success": True,
                        "payload": empty_on_403,
                        "error": "",
                        "status_code": response.status_code,
                        "attempts": attempts,
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

        print(
            f"[wb_api] endpoint={endpoint.name} method={request_method} "
            f"failed status={last_status} error={last_error}"
        )
        return {
            "success": False,
            "payload": [] if allow_204 else None,
            "error": last_error,
            "status_code": last_status,
            "attempts": attempts,
        }

    def extract_rows(self, payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        return self._extract_rows(payload, keys)
