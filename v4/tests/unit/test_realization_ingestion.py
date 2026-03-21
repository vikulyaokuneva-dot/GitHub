from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from v4.core.contracts import RunContext, RunMode
from v4.ingestion.api.client import ApiCallResult, WBApiClient
from v4.ingestion.api.realization import load_realization


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
        url="https://example/realization",
    )


class _SequenceClient:
    def __init__(self, responses: list[ApiCallResult]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get_json(self, endpoint, *, params=None, allow_statuses=None):  # noqa: ANN001, ANN201
        _ = endpoint, allow_statuses
        self.calls.append({"params": dict(params or {})})
        if not self._responses:
            raise AssertionError("unexpected extra get_json call")
        return self._responses.pop(0)

    @staticmethod
    def extract_rows(payload, keys):  # noqa: ANN001, ANN201
        return WBApiClient.extract_rows(payload, keys)

    @staticmethod
    def extract_rows_with_diagnostics(payload, keys, *, allow_single_dict=False, row_like_keys=None):  # noqa: ANN001, ANN201
        return WBApiClient.extract_rows_with_diagnostics(
            payload,
            keys,
            allow_single_dict=allow_single_dict,
            row_like_keys=row_like_keys,
        )


class TestRealizationIngestion(unittest.TestCase):
    def test_exact_target_date_returns_rows(self) -> None:
        client = _SequenceClient(
            [
                _response(
                    ok=True,
                    status_code=200,
                    payload=[{"rrd_id": 1, "rr_dt": "2026-03-19"}],
                )
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "3"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "ok")
        self.assertEqual(payload.status.debug.get("realization_reason"), "ok_with_rows")
        self.assertFalse(payload.status.debug.get("realization_fallback_used"))
        self.assertEqual(payload.status.debug.get("realization_source_date"), "2026-03-19")
        self.assertEqual(payload.status.debug.get("realization_lag_days"), 0)
        self.assertEqual(payload.status.debug.get("realization_http_status"), 200)
        self.assertEqual(payload.status.debug.get("realization_attempts"), 1)
        self.assertEqual(payload.status.debug.get("realization_record_count_raw"), 1)
        self.assertEqual(payload.status.debug.get("realization_request_params", {}).get("dateFrom"), "2026-03-19")
        self.assertEqual(payload.payload.get("realization_meta", {}).get("source_date"), "2026-03-19")
        self.assertEqual(len(client.calls), 1)

    def test_target_empty_previous_day_has_rows(self) -> None:
        client = _SequenceClient(
            [
                _response(ok=True, status_code=200, payload=[]),
                _response(ok=True, status_code=200, payload=[{"rrd_id": 2, "rr_dt": "2026-03-18"}]),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "3"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "partial")
        self.assertEqual(payload.status.debug.get("realization_reason"), "fallback_used")
        self.assertTrue(payload.status.debug.get("realization_fallback_used"))
        self.assertEqual(payload.status.debug.get("realization_source_date"), "2026-03-18")
        self.assertEqual(payload.status.debug.get("realization_lag_days"), 1)
        self.assertEqual(payload.status.rows_loaded, 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["params"], {"dateFrom": "2026-03-19", "dateTo": "2026-03-19", "limit": 100000, "rrdid": 0})
        self.assertEqual(client.calls[1]["params"], {"dateFrom": "2026-03-18", "dateTo": "2026-03-18", "limit": 100000, "rrdid": 0})

    def test_all_dates_empty_in_window(self) -> None:
        client = _SequenceClient(
            [
                _response(ok=True, status_code=200, payload=[]),
                _response(ok=True, status_code=204, payload=[]),
                _response(ok=True, status_code=200, payload=[]),
                _response(ok=True, status_code=200, payload=[]),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "2"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "missing")
        self.assertEqual(payload.status.debug.get("realization_reason"), "no_realization_in_window")
        self.assertFalse(payload.status.debug.get("realization_fallback_used"))
        self.assertIsNone(payload.status.debug.get("realization_source_date"))
        self.assertIsNone(payload.status.debug.get("realization_lag_days"))
        self.assertEqual(len(payload.status.debug.get("realization_attempt_log", [])), 4)
        self.assertTrue(payload.status.debug.get("realization_window_scan_used"))
        self.assertTrue(any("fallback window" in warning for warning in payload.status.warnings))
        self.assertEqual(len(client.calls), 4)

    def test_window_scan_fallback_recovers_rows(self) -> None:
        client = _SequenceClient(
            [
                _response(ok=True, status_code=200, payload=[]),
                _response(ok=True, status_code=200, payload=[]),
                _response(ok=True, status_code=200, payload=[]),
                _response(
                    ok=True,
                    status_code=200,
                    payload=[{"rrd_id": 3, "rr_dt": "2026-03-17"}],
                ),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "2"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "partial")
        self.assertEqual(payload.status.debug.get("realization_reason"), "fallback_used")
        self.assertTrue(payload.status.debug.get("realization_fallback_used"))
        self.assertTrue(payload.status.debug.get("realization_window_scan_used"))
        self.assertEqual(payload.status.debug.get("realization_source_date"), "2026-03-17")
        self.assertEqual(payload.status.debug.get("realization_lag_days"), 2)
        self.assertEqual(payload.status.rows_loaded, 1)
        self.assertEqual(len(payload.status.debug.get("realization_attempt_log", [])), 4)
        self.assertEqual(len(client.calls), 4)

    def test_http_204_is_valid_empty_response(self) -> None:
        client = _SequenceClient(
            [
                _response(ok=True, status_code=204, payload=[]),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "0"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "missing")
        self.assertEqual(payload.status.debug.get("realization_reason"), "no_data_for_date")
        self.assertEqual(payload.status.debug.get("realization_http_status"), 204)
        self.assertTrue(payload.status.debug.get("realization_empty_by_status"))
        self.assertIsNone(payload.status.error_code)

    def test_nonempty_payload_with_zero_extracted_rows_marks_parse_failed(self) -> None:
        client = _SequenceClient(
            [
                _response(ok=True, status_code=200, payload={"meta": {"page": 1}}),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "0"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "error")
        self.assertEqual(payload.status.debug.get("realization_reason"), "parse_failed")
        self.assertEqual(payload.status.error_code, "parse_failed")
        self.assertTrue(any("row extraction returned zero rows" in warning for warning in payload.status.warnings))

    def test_request_exception_maps_to_request_failed(self) -> None:
        client = _SequenceClient(
            [
                _response(
                    ok=False,
                    status_code=None,
                    payload=None,
                    error_code="request_exception",
                    error_message="timeout",
                ),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "3"}, clear=False):
            payload = load_realization(client, _context())

        self.assertEqual(payload.status.status.value, "error")
        self.assertEqual(payload.status.debug.get("realization_reason"), "request_failed")
        self.assertEqual(payload.status.error_code, "request_exception")
        self.assertEqual(payload.status.debug.get("realization_attempts"), 1)

    def test_nested_payload_and_json_string_are_extracted(self) -> None:
        nested_client = _SequenceClient(
            [
                _response(
                    ok=True,
                    status_code=200,
                    payload={"result": {"data": [{"rrd_id": 10, "rr_dt": "2026-03-19"}]}},
                ),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "0"}, clear=False):
            nested_payload = load_realization(nested_client, _context())
        self.assertEqual(nested_payload.status.status.value, "ok")
        self.assertEqual(nested_payload.status.rows_loaded, 1)
        self.assertEqual(nested_payload.status.debug.get("realization_extraction_mode"), "recursive_list")
        self.assertEqual(nested_payload.status.debug.get("realization_payload_origin"), "result.data")
        self.assertTrue(nested_payload.status.debug.get("realization_compat_used"))

        json_client = _SequenceClient(
            [
                _response(
                    ok=True,
                    status_code=200,
                    payload='[{"rrd_id": 11, "rr_dt": "2026-03-19"}]',
                ),
            ]
        )
        with patch.dict(os.environ, {"WB_MAX_FINANCE_LAG_DAYS": "0"}, clear=False):
            json_payload = load_realization(json_client, _context())
        self.assertEqual(json_payload.status.status.value, "ok")
        self.assertEqual(json_payload.status.rows_loaded, 1)
        self.assertEqual(json_payload.status.debug.get("realization_extraction_mode"), "top_list")


if __name__ == "__main__":
    unittest.main()
