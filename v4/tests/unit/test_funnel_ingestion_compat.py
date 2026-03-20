from __future__ import annotations

import unittest

from v4.core.contracts import RunContext, RunMode
from v4.ingestion.api.client import ApiCallResult
from v4.ingestion.api.funnel import load_funnel


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


class _StubClient:
    def __init__(self, response: ApiCallResult) -> None:
        self._response = response

    def post_json(self, *args, **kwargs) -> ApiCallResult:  # noqa: ANN002, ANN003
        _ = args, kwargs
        return self._response

    @staticmethod
    def extract_rows_with_diagnostics(payload, keys, *, allow_single_dict=False, row_like_keys=None):  # noqa: ANN001, ANN201
        from v4.ingestion.api.client import WBApiClient

        return WBApiClient.extract_rows_with_diagnostics(
            payload,
            keys,
            allow_single_dict=allow_single_dict,
            row_like_keys=row_like_keys,
        )


class TestFunnelIngestionCompat(unittest.TestCase):
    def test_statistic_selected_json_payload_is_extracted(self) -> None:
        response = ApiCallResult(
            ok=True,
            status_code=200,
            payload='{"data":{"items":[{"nmId":11,"statistic":{"selected":{"openCardCount":100,"addToCartCount":20,"orderCount":5,"buyoutCount":4}}}]}}',
            error_code=None,
            error_message=None,
            attempts=1,
            url="https://example/funnel",
        )
        payload = load_funnel(_StubClient(response), _context())
        self.assertEqual(payload.status.status.value, "ok")
        self.assertEqual(payload.status.rows_loaded, 1)
        self.assertTrue(payload.status.debug.get("funnel_compat_used"))
        self.assertEqual(payload.status.debug.get("funnel_payload_shape"), "structured")

    def test_single_dict_payload_uses_compat_fallback(self) -> None:
        response = ApiCallResult(
            ok=True,
            status_code=200,
            payload={
                "nmId": 11,
                "statistic": {"selected": {"openCardCount": 100, "addToCartCount": 20}},
            },
            error_code=None,
            error_message=None,
            attempts=1,
            url="https://example/funnel",
        )
        payload = load_funnel(_StubClient(response), _context())
        self.assertEqual(payload.status.status.value, "ok")
        self.assertEqual(payload.status.rows_loaded, 1)
        self.assertTrue(payload.status.debug.get("funnel_compat_used"))
        self.assertEqual(payload.status.debug.get("funnel_payload_shape"), "statistic_selected")
        self.assertEqual(payload.status.debug.get("funnel_extraction_mode"), "single_dict_fallback")


if __name__ == "__main__":
    unittest.main()

