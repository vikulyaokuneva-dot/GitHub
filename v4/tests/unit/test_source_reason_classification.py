from __future__ import annotations

import unittest

from v4.core.contracts import RunContext, RunMode
from v4.ingestion.api.client import ApiCallResult, WBApiClient
from v4.ingestion.api.funnel import load_funnel
from v4.ingestion.api.realization import load_realization


class _StubClient:
    def __init__(self, response: ApiCallResult) -> None:
        self._response = response

    def get_json(self, *args, **kwargs) -> ApiCallResult:  # noqa: ANN002, ANN003
        _ = args, kwargs
        return self._response

    def post_json(self, *args, **kwargs) -> ApiCallResult:  # noqa: ANN002, ANN003
        _ = args, kwargs
        return self._response

    @staticmethod
    def extract_rows(payload, keys):  # noqa: ANN001, ANN201
        return WBApiClient.extract_rows(payload, keys)


def _context() -> RunContext:
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date="2026-03-19",
        resolved_date="2026-03-19",
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


class TestSourceReasonClassification(unittest.TestCase):
    def test_realization_no_data_for_date_reason(self) -> None:
        response = ApiCallResult(
            ok=True,
            status_code=200,
            payload={"data": []},
            error_code=None,
            error_message=None,
            attempts=1,
            url="https://example/realization",
        )
        payload = load_realization(_StubClient(response), _context())
        self.assertEqual(payload.status.status.value, "missing")
        self.assertEqual(payload.status.debug.get("realization_reason"), "no_data_for_date")

    def test_realization_auth_error_reason(self) -> None:
        response = ApiCallResult(
            ok=False,
            status_code=403,
            payload=None,
            error_code="http_403",
            error_message="forbidden",
            attempts=1,
            url="https://example/realization",
        )
        payload = load_realization(_StubClient(response), _context())
        self.assertEqual(payload.status.status.value, "error")
        self.assertEqual(payload.status.debug.get("realization_reason"), "auth_error")

    def test_funnel_request_failed_reason(self) -> None:
        response = ApiCallResult(
            ok=False,
            status_code=500,
            payload=None,
            error_code="http_500",
            error_message="server error",
            attempts=1,
            url="https://example/funnel",
        )
        payload = load_funnel(_StubClient(response), _context())
        self.assertEqual(payload.status.status.value, "error")
        self.assertEqual(payload.status.debug.get("funnel_reason"), "request_failed")


if __name__ == "__main__":
    unittest.main()
