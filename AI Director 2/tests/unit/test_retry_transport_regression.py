"""Retry regressions for the WB compat transports (429/403/204, no double retry).

The audit pipeline reaches WB only through ``packages.compat.wb_sales_funnel_transport``,
so the policy declared there is the policy the pipeline actually runs. Four
failures are pinned here:

1. the funnel/operational transports declared no retry policy (implicit default:
   5 attempts, 30s header cap, no sleep budget) or a policy without
   ``max_retry_window_seconds`` -- a limiter window of hours was slept through
   request by request (6 x 30s) before the request failed anyway;
2. HTTP 204 ("no data for that day") was rejected by the finance transport
   because 204 carries no body bytes, turning the documented ``204 -> []``
   contract into a transport error;
3. exhausted-retry errors dropped ``error_text`` / ``Retry-After``, leaving the
   audit with a bare status code and no proof of rate limiting;
4. one 429 must produce one bounded transport cycle -- not a transport cycle
   with a loader loop on top of it.

Every sleep is patched: unit tests must never wait for a real delay.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from packages.accounts import (
    AccountRegistrationService,
    CredentialRef,
    SQLiteAccountRegistrationRepository,
)
from packages.compat.wb_sales_funnel_transport import (
    LegacyWBApiFinanceDetailTransport,
    LegacyWBApiLoadersTransport,
    LegacyWBApiOperationalTransport,
    LegacyWBApiSalesFunnelTransport,
)
from packages.wb_core.contracts import TenantAccountScope
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository
from wb_api_core.client import WBApiClient

DAY = date(2026, 10, 1)
RETRIEVED_AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    payload: Any = None,
    text: str | None = None,
    content: bytes = b"",
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    if text is None:
        text = "too many requests" if status_code == 429 else ""
    response.text = text
    response.json.return_value = payload if payload is not None else {"ok": True}
    response.content = content
    return response


class _RecordingClient:
    """Fake client that records every ``request_json`` kwargs (policies)."""

    statistics_base_url = "https://statistics-api.wildberries.ru"
    analytics_base_url = "https://seller-analytics-api.wildberries.ru"
    finance_base_url = "https://finance-api.wildberries.ru"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        endpoint = str(kwargs.get("endpoint_name"))
        if endpoint in {"orders", "sales"}:
            return {
                "success": True,
                "payload": [{"date": "2026-10-01"}],
                "payload_bytes": b'[{"date":"2026-10-01"}]',
                "status_code": 200,
                "attempts": 1,
            }
        if endpoint == "finance_detail":
            return {
                "success": True,
                "payload": {"data": []},
                "payload_bytes": b'{"data":[]}',
                "status_code": 200,
                "attempts": 1,
            }
        return {
            "success": True,
            "payload": {"data": {"products": []}},
            "status_code": 200,
            "attempts": 1,
        }


def test_every_compat_transport_declares_the_bounded_rate_limit_policy() -> None:
    client = _RecordingClient()

    LegacyWBApiLoadersTransport(client).load_cabinet_commerce(operational_date=DAY)
    LegacyWBApiOperationalTransport(client).fetch_orders(operational_date=DAY)
    LegacyWBApiSalesFunnelTransport(client).fetch_sales_funnel_products(operational_date=DAY)
    LegacyWBApiFinanceDetailTransport(client).fetch_finance_detail(operational_date=DAY)

    assert len(client.calls) == 4
    for call in client.calls:
        endpoint = str(call.get("endpoint_name"))
        policy = call.get("retry_policy")
        assert policy is not None, f"{endpoint}: the retry policy must be explicit"
        assert 429 in policy["retryable_statuses"], f"{endpoint}: 429 must be retryable"
        assert policy["max_attempts"] >= 2, f"{endpoint}: a retryable 429 needs a second attempt"
        assert float(policy["max_delay_seconds"]) > 0, f"{endpoint}: header-derived wait must be capped"
        assert (
            float(policy["max_retry_window_seconds"]) > 0
        ), f"{endpoint}: total sleep must be bounded (no sleeping through the limiter window)"


def test_long_limiter_window_is_not_slept_through_by_the_funnel_transport() -> None:
    """``Retry-After: 3582`` (an hour away) must stop after one bounded sleep."""

    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(429, headers={"Retry-After": "3582"}),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        with pytest.raises(RuntimeError) as raised:
            LegacyWBApiLoadersTransport(client).load_cabinet_commerce(operational_date=DAY)

    # Before the fix: 6 transport calls and 5 x 30s = 150s of sleeping.
    assert request_mock.call_count == 2
    assert sleep_mock.call_count == 1
    total_sleep = sum(float(call.args[0]) for call in sleep_mock.call_args_list)
    assert total_sleep <= 20.0

    message = str(raised.value)
    assert "status 429" in message
    assert "retry_window_exhausted" in message
    assert "retry_after=3582" in message


def test_exhausted_finance_429_keeps_the_rate_limit_diagnostics() -> None:
    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(429, headers={"Retry-After": "1"}),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        with pytest.raises(RuntimeError) as raised:
            LegacyWBApiFinanceDetailTransport(client).fetch_finance_detail(operational_date=DAY)

    assert request_mock.call_count <= 3
    assert sleep_mock.call_count == request_mock.call_count - 1  # one bounded cycle, then stop

    message = str(raised.value)
    assert "status 429" in message
    assert "rate_limit_headers" in message
    assert "retry_after=1" in message
    # Never a fake success: the failure stays an exception, not an empty payload.
    assert message.startswith("finance_detail WB request failed with status 429")


def test_403_is_not_retried_by_the_finance_transport() -> None:
    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(403, text="token does not satisfy the required scopes"),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        with pytest.raises(RuntimeError) as raised:
            LegacyWBApiFinanceDetailTransport(client).fetch_finance_detail(operational_date=DAY)

    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0
    assert "status 403" in str(raised.value)


def test_finance_204_keeps_the_empty_list_contract() -> None:
    """Scenario E: a 204 day stays ``([], bytes)`` instead of raising."""

    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(204),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        payload, raw_bytes = LegacyWBApiFinanceDetailTransport(client).fetch_finance_detail(operational_date=DAY)

    assert payload == []
    assert raw_bytes == b"[]"
    # RawObject requires raw bytes that decode to the payload without rewrap.
    assert json.loads(raw_bytes) == payload
    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_finance_200_returns_the_payload_with_the_original_bytes() -> None:
    client = WBApiClient(token="token")
    body = b'{"data":[{"rrdId":1,"rrDate":"2026-10-01"}]}'

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(200, payload={"data": [{"rrdId": 1, "rrDate": "2026-10-01"}]}, content=body),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        payload, raw_bytes = LegacyWBApiFinanceDetailTransport(client).fetch_finance_detail(operational_date=DAY)

    assert payload == {"data": [{"rrdId": 1, "rrDate": "2026-10-01"}]}
    assert raw_bytes == body  # 200 keeps the exact response bytes
    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_a_single_429_is_retried_once_at_one_layer_only() -> None:
    """Scenario G: no transport cycle wrapped in a loader/compat loop."""

    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        side_effect=[
            _response(429, headers={"Retry-After": "1"}),
            _response(200, payload={"data": {"products": []}}),
        ],
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        result = LegacyWBApiLoadersTransport(client).load_cabinet_commerce(operational_date=DAY)

    assert result["payload"]["data"] == {"products": []}
    assert request_mock.call_count == 2  # the 429 itself + exactly one retry
    assert sleep_mock.call_count == 1
    assert float(sleep_mock.call_args[0][0]) == 1.0


def _scope(tmp_path: Path) -> TenantAccountScope:
    accounts = SQLiteAccountRegistrationRepository(tmp_path / "shared.sqlite3")
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="retry_regression_seller",
        credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL"),
    )
    return registration.scope


def test_exhausted_429_never_persists_an_empty_raw_object(tmp_path: Path) -> None:
    """Scenario C end to end: a rate-limited day stays missing, never empty."""

    scope = _scope(tmp_path)
    repository = SQLiteRawObjectRepository(tmp_path / "shared.sqlite3")
    service = WBDailyIngestionService(
        repository=repository,
        loaders=LegacyWBApiLoadersTransport(WBApiClient(token="token")),
    )

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(429, headers={"Retry-After": "1"}),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        diagnostics = service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    joined = "\n".join(diagnostics)
    assert "source_unavailable:orders" in joined
    assert "429" in joined
    assert "rate_limit_headers" in joined  # the audit can prove rate limiting
    assert repository.list(scope=scope) == ()  # 429 never becomes an empty raw
    # Bounded: every source retries within its own budget, none loops forever.
    assert request_mock.call_count <= 20
    assert sleep_mock.call_count < request_mock.call_count
