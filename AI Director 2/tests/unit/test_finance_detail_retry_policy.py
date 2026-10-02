"""The finance_detail source must retry HTTP 429 with a bounded sleep budget.

A single 429 from the WB per-seller limiter used to fail this source on the
first attempt, so no raw object was persisted and the financial metrics stayed
``missing``. The transport keeps using the headers the client already parses
(``Retry-After`` / ``X-Ratelimit-Retry`` / ``X-Ratelimit-Reset``); these tests
only pin the retry policy it hands to ``request_json``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from packages.compat.wb_sales_funnel_transport import LegacyWBApiFinanceDetailTransport


class _RecordingFinanceClient:
    finance_base_url = "https://finance-api.wildberries.ru"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "success": True,
            "payload": {"data": []},
            "payload_bytes": b"{}",
            "status_code": 200,
            "attempts": 1,
        }


def test_finance_detail_transport_retries_429() -> None:
    client = _RecordingFinanceClient()

    LegacyWBApiFinanceDetailTransport(client).fetch_finance_detail(
        operational_date=date(2026, 8, 27),
    )

    assert len(client.calls) == 1
    policy = client.calls[0]["retry_policy"]
    assert 429 in policy["retryable_statuses"], "429 must be retryable for finance_detail"
    assert policy["max_attempts"] >= 2, "a retryable 429 needs a second attempt"
    assert float(policy["max_delay_seconds"]) > 0, "header-derived wait must be capped"
    assert float(policy["max_retry_window_seconds"]) > 0, "total sleep must be bounded"
