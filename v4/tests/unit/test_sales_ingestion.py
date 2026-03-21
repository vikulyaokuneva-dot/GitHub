from __future__ import annotations

import unittest

from v4.core.contracts import RunContext, RunMode
from v4.ingestion.api.client import ApiCallResult, WBApiClient
from v4.ingestion.api.sales import load_sales


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


def _response(
    *,
    ok: bool,
    status_code: int | None,
    payload,
    error_code: str | None = None,
    error_message: str | None = None,
    attempts: int = 1,
) -> ApiCallResult:
    return ApiCallResult(
        ok=ok,
        status_code=status_code,
        payload=payload,
        error_code=error_code,
        error_message=error_message,
        attempts=attempts,
        url="https://example/sales",
    )


class _SingleResponseClient:
    def __init__(self, response: ApiCallResult) -> None:
        self._response = response

    def get_json(self, endpoint, *, params=None, allow_statuses=None):  # noqa: ANN001, ANN201
        _ = endpoint, params, allow_statuses
        return self._response

    @staticmethod
    def extract_rows_with_diagnostics(payload, keys, *, allow_single_dict=False, row_like_keys=None):  # noqa: ANN001, ANN201
        return WBApiClient.extract_rows_with_diagnostics(
            payload,
            keys,
            allow_single_dict=allow_single_dict,
            row_like_keys=row_like_keys,
        )


class TestSalesIngestion(unittest.TestCase):
    def test_nonempty_payload_with_zero_extracted_rows_marks_parse_failed(self) -> None:
        client = _SingleResponseClient(
            _response(
                ok=True,
                status_code=200,
                payload={"meta": {"page": 1}},
            )
        )

        payload = load_sales(client, _context())

        self.assertEqual(payload.status.status.value, "error")
        self.assertEqual(payload.status.debug.get("sales_reason"), "parse_failed")
        self.assertEqual(payload.status.error_code, "parse_failed")
        self.assertTrue(any("row extraction returned zero rows" in warning for warning in payload.status.warnings))

    def test_empty_payload_marks_missing(self) -> None:
        client = _SingleResponseClient(
            _response(
                ok=True,
                status_code=200,
                payload=[],
            )
        )

        payload = load_sales(client, _context())

        self.assertEqual(payload.status.status.value, "missing")
        self.assertEqual(payload.status.debug.get("sales_reason"), "ok_empty_payload")
        self.assertIsNone(payload.status.error_code)

    def test_nested_payload_rows_marks_ok(self) -> None:
        client = _SingleResponseClient(
            _response(
                ok=True,
                status_code=200,
                payload={"result": {"data": [{"saleID": "s1", "date": "2026-03-19"}]}},
            )
        )

        payload = load_sales(client, _context())

        self.assertEqual(payload.status.status.value, "ok")
        self.assertEqual(payload.status.rows_loaded, 1)
        self.assertEqual(payload.status.debug.get("sales_reason"), "ok_with_rows")
        self.assertEqual(payload.status.debug.get("sales_extraction_mode"), "recursive_list")
        self.assertEqual(payload.status.debug.get("sales_payload_origin"), "result.data")
        self.assertTrue(payload.status.debug.get("sales_compat_used"))


if __name__ == "__main__":
    unittest.main()
