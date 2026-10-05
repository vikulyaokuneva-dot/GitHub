"""Regression: a failed source must keep the proof of *why* it failed.

Live evidence (2026-10-05, seller 4297720): the ``/audit`` diagnostics cut the
WB failure reason at 200 characters, i.e. in the middle of the official error
JSON, so ``origin`` / ``requestId`` and the whole ``rate_limit_headers`` block
disappeared::

    source_unavailable:finance_detail: finance_detail WB request failed with
    status 429: retry_window_exhausted: 429: {"status":429,...,"detail":"rate
    limit exceeded, retry after the period specified in the X-RateLimit-Retry
    header"

while the raw response really carried ``origin=ag-finance``,
``requestId=0b22e5eb...`` and ``x_ratelimit_retry=18236`` (~5h). The audit
therefore could not prove whether a source is permission-blocked (stocks, 403
from ``ag-contentanalytics``) or rate-limited (finance, 429 from
``ag-finance``) - exactly the distinction this stage has to demonstrate.

The tests pin the bodies/headers WB returned for this account and assert that
both raise sites keep status, request line, official detail/origin/requestId
and the rate-limit headers, while staying bounded.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

from packages.compat.wb_sales_funnel_transport import (
    LegacyWBApiFinanceDetailTransport,
    LegacyWBApiLoadersTransport,
    LegacyWBApiOperationalTransport,
)
from packages.wb_core.contracts import TenantAccountScope
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.source_diagnostics import describe_source_failure
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository
from wb_api_core.client import WBApiClient  # type: ignore[import-untyped]

DAY = date(2026, 10, 4)
RETRIEVED_AT = datetime(2026, 10, 5, 15, 15, 53, tzinfo=UTC)

FINANCE_429_BODY = (
    '{"status":429,"statusText":"Too Many Requests","title":"Too Many Requests",'
    '"detail":"rate limit exceeded, retry after the period specified in the X-RateLimit-Retry header",'
    '"requestId":"0b22e5ebd9142068cc514b169b07742d","origin":"ag-finance",'
    '"timestamp":"2026-10-05T15:22:15Z"}'
)
FINANCE_429_REASON = (
    f"retry_window_exhausted: 429: {FINANCE_429_BODY}"
    "; rate_limit_headers: retry_after=, x_ratelimit_retry=18236, x_ratelimit_reset=18236, "
    "x_ratelimit_remaining=0"
)
STOCKS_403_BODY = (
    '{"status":403,"statusText":"Forbidden","title":"Forbidden",'
    '"detail":"token does not satisfy additional requirements",'
    '"requestId":"22514997079d314d54d209e38f8dfd94","origin":"ag-contentanalytics",'
    '"timestamp":"2026-10-05T15:15:53Z"}'
)
# statistics-api global limiter body, as documented in docs/STAGE_20_7_REPORT.md.
STATISTICS_429_BODY = (
    '{"status":429,"statusText":"Too Many Requests","title":"Too Many Requests",'
    '"detail":"Limited by global limiter, per seller 4297720",'
    '"requestId":"f3d1b5c2a9e84d1f9c7b6a5d4e3f2a1b","origin":"s2s-api",'
    '"timestamp":"2026-10-05T15:15:53Z"}'
)

_SCOPE = TenantAccountScope(
    tenant_id=UUID("8eeba4a7-3f9c-457e-90a9-fbd3b28a0318"),
    account_id=UUID("fed4abfa-bbda-4988-9202-e86d6fcc2b3c"),
)


def _response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    text: str = "",
) -> MagicMock:
    """A real-shaped ``requests.Response``: body text drives both json and content."""

    def _parse_body() -> Any:
        return json.loads(text)

    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = text
    response.content = text.encode("utf-8")
    response.json.side_effect = _parse_body
    return response


def _finance_failure(**kwargs: Any) -> dict[str, Any]:
    return {
        "endpoint": "finance_detail",
        "path": "/api/finance/v1/sales-reports/detailed",
        "method": "POST",
        "base_url": "https://finance-api.wildberries.ru",
        "status_code": 429,
        "final_failure_reason": FINANCE_429_REASON,
        **kwargs,
    }


def test_finance_429_failure_keeps_the_rate_limit_proof() -> None:
    """The rate-limit proof must survive a full-size WB error body."""

    reason = _finance_failure()["final_failure_reason"]
    # The defect this replaces: a prefix cut of the same reason kept neither
    # the official origin/requestId nor any rate-limit header.
    assert "origin" not in reason[:200]
    assert "rate_limit_headers" not in reason[:200]

    message = describe_source_failure(endpoint_name="finance_detail", response=_finance_failure())

    assert message.startswith("finance_detail WB request failed with status 429")
    assert "POST https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed" in message
    assert "retry_window_exhausted" in message
    assert "rate limit exceeded" in message
    assert "origin=ag-finance" in message
    assert "requestId=0b22e5ebd9142068cc514b169b07742d" in message
    assert "rate_limit_headers" in message
    assert "x_ratelimit_retry=18236" in message
    assert "x_ratelimit_remaining=0" in message
    assert len(message) <= 900


def test_stocks_403_failure_keeps_the_permission_proof() -> None:
    """403 must still name the refusing zone: permission vs rate limit differ."""

    message = describe_source_failure(
        endpoint_name="stocks",
        response={
            "path": "/api/analytics/v1/stocks-report/wb-warehouses",
            "method": "POST",
            "base_url": "https://seller-analytics-api.wildberries.ru",
            "status_code": 403,
            "final_failure_reason": f"403: {STOCKS_403_BODY}",
        },
    )

    assert message.startswith("stocks WB request failed with status 403")
    assert "POST https://seller-analytics-api.wildberries.ru/api/analytics/v1/stocks-report/wb-warehouses" in message
    assert "token does not satisfy additional requirements" in message
    assert "origin=ag-contentanalytics" in message
    assert "requestId=22514997079d314d54d209e38f8dfd94" in message
    assert "rate_limit_headers" not in message
    assert len(message) <= 900


def test_financial_transport_failure_is_bounded_and_provable() -> None:
    """One real 429 cycle: bounded retries, and the raised message keeps the proof."""

    client = WBApiClient(token="test-token")
    transport = LegacyWBApiFinanceDetailTransport(client)
    failure = _response(429, headers={"X-RateLimit-Retry": "18236"}, text=FINANCE_429_BODY)

    with patch("wb_api_core.client.requests.request", return_value=failure) as request_mock, patch(
        "wb_api_core.client.time.sleep"
    ) as sleep_mock:
        try:
            transport.fetch_finance_detail(operational_date=DAY)
        except RuntimeError as exc:
            message = str(exc)
        else:  # pragma: no cover - the failure must raise
            raise AssertionError("the 429 must surface as an unavailable source, not as data")

    assert request_mock.call_count <= 3
    assert sleep_mock.call_count <= 1
    assert message.startswith("finance_detail WB request failed with status 429")
    assert "retry_window_exhausted" in message
    assert "origin=ag-finance" in message
    assert "x_ratelimit_retry=18236" in message


def test_daily_ingestion_diagnostics_keep_the_403_proof(tmp_path: Path) -> None:
    """The audit-facing diagnostic of a real loader path carries the proof."""

    service = WBDailyIngestionService(
        repository=SQLiteRawObjectRepository(tmp_path / "source_failure_diagnostics.sqlite3"),
        loaders=LegacyWBApiLoadersTransport(WBApiClient(token="test-token")),
    )
    forbidden = _response(403, text=STOCKS_403_BODY)

    with patch("wb_api_core.client.requests.request", return_value=forbidden), patch(
        "wb_api_core.client.time.sleep"
    ):
        diagnostics = service.ingest(scope=_SCOPE, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    stocks_line = next((item for item in diagnostics if item.startswith("source_unavailable:stocks:")), None)
    assert stocks_line is not None, diagnostics
    assert "status 403" in stocks_line
    assert "origin=ag-contentanalytics" in stocks_line
    assert "token does not satisfy additional requirements" in stocks_line
    assert "/api/analytics/v1/stocks-report/wb-warehouses" in stocks_line
    # 403 is not retryable: one refused request, no sleep loop.
    assert "retry_after" not in stocks_line


def test_unparsed_body_is_excerpted_and_credentials_never_leak() -> None:
    """No raw dump: long bodies are bounded and credential-shaped fields dropped."""

    long_detail = "upstream failure " * 40
    body = (
        '{"status":500,"detail":"' + long_detail + '","token":"wb_secret_value","origin":"ag-seller"}'
    )
    message = describe_source_failure(
        endpoint_name="orders",
        response={
            "path": "/api/v1/supplier/orders",
            "method": "GET",
            "base_url": "https://statistics-api.wildberries.ru",
            "status_code": 500,
            "final_failure_reason": f"500: {body}",
        },
    )

    assert "wb_secret_value" not in message
    assert "origin=ag-seller" in message
    assert len(message) <= 900
    assert "upstream failure" in message


def test_non_json_body_is_kept_verbatim() -> None:
    """A plain-text WB body must stay readable (existing fixtures rely on it)."""

    message = describe_source_failure(
        endpoint_name="sales",
        response={
            "status_code": 403,
            "error_text": "403: token does not satisfy the required scopes",
        },
    )

    assert "403: token does not satisfy the required scopes" in message


def test_missing_fields_still_produce_a_useful_message() -> None:
    """Hand-built transports in tests carry only part of the mapping."""

    assert describe_source_failure(endpoint_name="orders", response=None) == (
        "orders WB request failed with status None"
    )
    assert describe_source_failure(
        endpoint_name="orders",
        response={"status_code": None},
        fallback="loader transport failed",
    ).endswith(": loader transport failed")


def test_structured_rate_limit_fields_fill_in_when_the_reason_has_no_tail() -> None:
    """Structured debug fields are a second source of the proof."""

    message = describe_source_failure(
        endpoint_name="advertising_performance",
        response={
            "path": "/api/advert/v2/adverts",
            "method": "GET",
            "status_code": 429,
            "error_text": "429: too many requests",
            "x_ratelimit_retry": "3582",
            "x_ratelimit_remaining": "0",
        },
    )

    assert "rate_limit_headers" in message
    assert "x_ratelimit_retry=3582" in message
    assert "x_ratelimit_remaining=0" in message
    assert "429: too many requests" in message


def test_operational_204_is_an_empty_day_not_a_failed_source() -> None:
    """``_request_array`` must honor the same ``204 -> []`` contract as the loaders."""

    transport = LegacyWBApiOperationalTransport(WBApiClient(token="test-token"))

    with patch("wb_api_core.client.requests.request", return_value=_response(204)), patch(
        "wb_api_core.client.time.sleep"
    ):
        rows, raw_bytes = transport.fetch_orders(operational_date=DAY)

    assert rows == []
    assert raw_bytes == b"[]"


def test_operational_success_extracts_the_wb_data_array() -> None:
    """The real answer shape is ``{"data": [...]}``: rows extracted, bytes verbatim."""

    transport = LegacyWBApiOperationalTransport(WBApiClient(token="test-token"))
    body = '{"data":[{"date":"2026-10-04T10:00:00","srid":"x"}]}'

    with patch("wb_api_core.client.requests.request", return_value=_response(200, text=body)), patch(
        "wb_api_core.client.time.sleep"
    ):
        rows, raw_bytes = transport.fetch_sales(operational_date=DAY)

    assert rows == [{"date": "2026-10-04T10:00:00", "srid": "x"}]
    assert raw_bytes == body.encode("utf-8")


def test_operational_success_accepts_a_bare_json_array() -> None:
    transport = LegacyWBApiOperationalTransport(WBApiClient(token="test-token"))
    body = '[{"date":"2026-10-04T10:00:00"}]'

    with patch("wb_api_core.client.requests.request", return_value=_response(200, text=body)), patch(
        "wb_api_core.client.time.sleep"
    ):
        rows, raw_bytes = transport.fetch_orders(operational_date=DAY)

    assert rows == [{"date": "2026-10-04T10:00:00"}]
    assert raw_bytes == body.encode("utf-8")


def test_operational_403_is_not_retried_and_keeps_the_permission_proof() -> None:
    """A refused token: one request, no sleep, official origin in the message."""

    transport = LegacyWBApiOperationalTransport(WBApiClient(token="test-token"))
    failure = _response(403, text=STOCKS_403_BODY)

    with patch("wb_api_core.client.requests.request", return_value=failure) as request_mock, patch(
        "wb_api_core.client.time.sleep"
    ) as sleep_mock:
        try:
            transport.fetch_orders(operational_date=DAY)
        except RuntimeError as exc:
            message = str(exc)
        else:  # pragma: no cover - the failure must raise
            raise AssertionError("the 403 must surface as an unavailable source, not as data")

    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0
    assert message.startswith("orders WB request failed with status 403")
    assert "origin=ag-contentanalytics" in message
    assert "rate_limit_headers" not in message


def test_operational_malformed_payload_is_rejected() -> None:
    """A non-array body must fail loudly, never as an empty day."""

    transport = LegacyWBApiOperationalTransport(WBApiClient(token="test-token"))

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(200, text='{"data": {"unexpected": true}}'),
    ), patch("wb_api_core.client.time.sleep"):
        try:
            transport.fetch_orders(operational_date=DAY)
        except ValueError as exc:
            assert "orders response must be a JSON array of objects" in str(exc)
        else:  # pragma: no cover - malformed data must not pass as data
            raise AssertionError("a malformed payload must not be accepted")


def test_operational_429_stops_bounded_and_keeps_the_proof() -> None:
    """429 on orders: bounded retries, then a message that proves the limit."""

    transport = LegacyWBApiOperationalTransport(WBApiClient(token="test-token"))
    failure = _response(429, headers={"X-RateLimit-Retry": "10299"}, text=STATISTICS_429_BODY)

    with patch("wb_api_core.client.requests.request", return_value=failure) as request_mock, patch(
        "wb_api_core.client.time.sleep"
    ) as sleep_mock:
        try:
            transport.fetch_orders(operational_date=DAY)
        except RuntimeError as exc:
            message = str(exc)
        else:  # pragma: no cover - the failure must raise
            raise AssertionError("the 429 must surface as an unavailable source, not as data")

    assert request_mock.call_count <= 3
    assert sleep_mock.call_count <= 1
    assert message.startswith("orders WB request failed with status 429")
    assert "GET https://statistics-api.wildberries.ru/api/v1/supplier/orders" in message
    assert "retry_window_exhausted" in message
    assert "x_ratelimit_retry=10299" in message
    assert "origin=s2s-api" in message
