"""429 must be retryable for the supplier-statistics and advertising loaders.

The per-seller WB limiter answers HTTP 429 with ``Retry-After`` /
``X-Ratelimit-Retry`` (and ``X-Ratelimit-Reset``). Until now ``load_orders``,
``load_sales`` and ``load_ads`` passed ``retryable_statuses=(500, 502, 503, 504)``
so a single 429 failed the source on the first attempt: no raw object was
persisted and the metric stayed ``missing``. These tests pin the policy handed
to ``request_json`` and its behaviour at the client boundary, using the headers
the client already parses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any
from unittest.mock import MagicMock, patch

from wb_api_core.client import (
    ADVERT_STATS_PATH,
    ADVERTS_PATH,
    ORDERS_PATH,
    SALES_PATH,
    WBApiClient,
    rate_limited_retry_policy,
)
from wb_api_core.loaders import load_ads, load_orders, load_sales


def _assert_rate_limited_policy(policy: dict[str, Any], *, endpoint: str) -> None:
    assert 429 in policy["retryable_statuses"], f"{endpoint}: 429 must be retryable"
    assert policy["max_attempts"] >= 2, f"{endpoint}: a retryable 429 needs a second attempt"
    assert float(policy["max_delay_seconds"]) > 0, f"{endpoint}: header-derived wait must be capped"
    assert float(policy["max_retry_window_seconds"]) > 0, f"{endpoint}: total sleep must be bounded"


class _RecordingClient:
    """Minimal fake client that records every ``request_json`` kwargs."""

    statistics_base_url = "https://statistics-api.wildberries.ru"
    advert_base_url = "https://advert-api.wildberries.ru"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        endpoint = str(kwargs.get("endpoint_name"))
        if endpoint == "ads_adverts":
            return {
                "success": True,
                "payload": {"adverts": [{"advertId": 101}]},
                "status_code": 200,
            }
        if endpoint == "ads_stats":
            return {
                "success": True,
                "payload": [
                    {
                        "days": [
                            {
                                "nm": [
                                    {
                                        "nmId": 1010101,
                                        "sum": 123.45,
                                        "impressions": 1000.0,
                                        "clicks": 50.0,
                                        "orders": 2.0,
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "status_code": 200,
            }
        return {
            "success": True,
            "payload": [{"date": str(kwargs.get("params", {}).get("dateFrom"))}],
            "status_code": 200,
        }

    @staticmethod
    def extract_rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        return WBApiClient.extract_rows(payload, keys)


def test_load_orders_passes_rate_limited_policy() -> None:
    client = _RecordingClient()

    load_orders(client, "2026-09-27")

    assert len(client.calls) == 1
    assert client.calls[0]["path"] == ORDERS_PATH
    _assert_rate_limited_policy(client.calls[0]["retry_policy"], endpoint="orders")


def test_load_sales_passes_rate_limited_policy() -> None:
    client = _RecordingClient()

    load_sales(client, "2026-09-27")

    assert len(client.calls) == 1
    assert client.calls[0]["path"] == SALES_PATH
    _assert_rate_limited_policy(client.calls[0]["retry_policy"], endpoint="sales")


def test_load_ads_passes_rate_limited_policy_for_list_and_stats() -> None:
    client = _RecordingClient()

    load_ads(client, "2026-09-27")

    assert [call["path"] for call in client.calls] == [ADVERTS_PATH, ADVERT_STATS_PATH]
    for call in client.calls:
        _assert_rate_limited_policy(
            call["retry_policy"],
            endpoint=str(call.get("endpoint_name")),
        )


def _response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    payload: object | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = "too many requests" if status_code == 429 else ""
    response.json.return_value = payload if payload is not None else {"ok": True}
    return response


def test_rate_limited_policy_retries_429_and_honours_retry_after() -> None:
    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        side_effect=[_response(429, headers={"Retry-After": "4"}), _response(200)],
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is True
    assert response["attempts"] == 2
    assert request_mock.call_count == 2
    sleep_mock.assert_called_once_with(4.0)
    assert response["retry_after"] == "4"


def test_rate_limited_policy_retries_429_without_rate_limit_headers() -> None:
    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        side_effect=[_response(429), _response(200)],
    ), patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="sales",
            path=SALES_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is True
    assert response["attempts"] == 2
    delay = float(sleep_mock.call_args[0][0])
    # base_delay_seconds (3.0) plus at most jitter_ratio (0.1) of it
    assert 3.0 <= delay <= 3.3


def test_rate_limited_policy_gives_up_fast_when_limiter_window_is_long() -> None:
    """A window measured in hours must not be slept through request by request."""
    client = WBApiClient(token="token")
    headers = {"X-Ratelimit-Retry": "3582"}

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(429, headers=headers),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="finance_detail",
            path="/api/finance/v1/sales-reports/detailed",
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is False
    assert response["status_code"] == 429
    assert response["attempts"] == 2
    assert request_mock.call_count == 2
    # one bounded header-derived sleep, then the retry window guard stops it
    assert sleep_mock.call_count == 1
    assert float(sleep_mock.call_args[0][0]) <= 15.0
    assert "retry_window_exhausted" in str(response["final_failure_reason"])
    assert response["x_ratelimit_retry"] == "3582"


def test_rate_limited_policy_keeps_server_error_retries() -> None:
    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        side_effect=[_response(503), _response(503), _response(200)],
    ), patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is True
    assert response["attempts"] == 3
    assert sleep_mock.call_count == 2


# --- Retry-After variants: seconds, HTTP-date, missing/negative hints ---------

_FIXED_EPOCH = 4102444800.0  # 2100-01-01T00:00:00Z so HTTP-date delays are exact


def _http_date(offset_seconds: float, *, with_zone: bool) -> str:
    moment = datetime.fromtimestamp(_FIXED_EPOCH + offset_seconds, tz=UTC)
    if with_zone:
        return format_datetime(moment, usegmt=True)
    # A zone-less HTTP-date: parsedate_to_datetime returns a naive datetime.
    return moment.strftime("%a, %d %b %Y %H:%M:%S")


def _one_429_then_success(headers: dict[str, str]):
    return patch(
        "wb_api_core.client.requests.request",
        side_effect=[_response(429, headers=headers), _response(200)],
    )


def test_retry_after_http_date_is_honoured() -> None:
    client = WBApiClient(token="token")

    with _one_429_then_success({"Retry-After": _http_date(2.0, with_zone=True)}), patch(
        "wb_api_core.client.time.time", return_value=_FIXED_EPOCH
    ), patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is True
    sleep_mock.assert_called_once_with(2.0)


def test_retry_after_http_date_without_zone_is_read_as_utc() -> None:
    """A naive HTTP-date must not collapse to a 0s delay in a local timezone.

    Before this fix ``parsed.timestamp()`` read the zone-less date in the local
    timezone (UTC+3 in Europe/Moscow), which turned a real two-second wait into
    a negative value clamped to zero: the retry hammered the limiter instead of
    honouring ``Retry-After``.
    """

    client = WBApiClient(token="token")

    with _one_429_then_success({"Retry-After": _http_date(2.0, with_zone=False)}), patch(
        "wb_api_core.client.time.time", return_value=_FIXED_EPOCH
    ), patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is True
    sleep_mock.assert_called_once_with(2.0)


def test_retry_after_never_produces_a_negative_delay() -> None:
    """Past HTTP-date and negative seconds both clamp to 0, never below."""

    for header_value in (_http_date(-3600.0, with_zone=True), "-5", "-0.5"):
        client = WBApiClient(token="token")
        with _one_429_then_success({"Retry-After": header_value}), patch(
            "wb_api_core.client.time.time", return_value=_FIXED_EPOCH
        ), patch("wb_api_core.client.time.sleep") as sleep_mock:
            response = client.request_json(
                endpoint_name="orders",
                path=ORDERS_PATH,
                retry_policy=rate_limited_retry_policy(),
            )

        assert response["success"] is True, header_value
        assert sleep_mock.call_count == 1, header_value
        assert float(sleep_mock.call_args[0][0]) == 0.0, header_value


# --- A-G retry behaviour at the client/loader boundary ------------------------


def test_exhausted_429_is_reported_as_failure_not_as_an_empty_payload() -> None:
    """Scenario C: exhausting the attempts must never yield ``[]``/success."""

    client = WBApiClient(token="token")
    policy = rate_limited_retry_policy()

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(429, headers={"Retry-After": "1"}),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=policy,
        )

    assert response["success"] is False
    assert response["status_code"] == 429
    assert response["payload"] is None  # not [] and not {}
    assert response["attempts"] == policy["max_attempts"]
    assert request_mock.call_count == policy["max_attempts"]
    assert sleep_mock.call_count == policy["max_attempts"] - 1
    assert "rate_limit_headers" in str(response["final_failure_reason"])


def test_403_is_not_retried_by_the_rate_limited_policy() -> None:
    """Scenario D: an HTTP error the policy does not retryable must run once."""

    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(403),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is False
    assert response["status_code"] == 403
    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_204_keeps_the_empty_list_contract_in_the_loader() -> None:
    """Scenario E: ``204 -> []`` stays a successful empty day, not a failure."""

    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(204),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        result = load_orders(client, "2026-10-01")

    assert result["rows_raw"] == []
    assert result["debug"]["success"] is True
    assert result["debug"]["status_code"] == 204
    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_200_returns_the_payload_without_any_retry() -> None:
    """Scenario F: a plain 200 keeps the payload untouched and sleeps nothing."""

    client = WBApiClient(token="token")
    payload = [{"date": "2026-10-01", "srid": "srid-1"}]

    with patch(
        "wb_api_core.client.requests.request",
        return_value=_response(200, payload=payload),
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        response = client.request_json(
            endpoint_name="orders",
            path=ORDERS_PATH,
            retry_policy=rate_limited_retry_policy(),
        )

    assert response["success"] is True
    assert response["payload"] == payload
    assert response["attempts"] == 1
    assert request_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_one_429_produces_exactly_one_transport_retry_cycle() -> None:
    """Scenario G: one 429 -> one bounded cycle, never a second independent one."""

    client = WBApiClient(token="token")

    with patch(
        "wb_api_core.client.requests.request",
        side_effect=[
            _response(429, headers={"Retry-After": "1"}),
            _response(200, payload=[{"date": "2026-10-01", "srid": "srid-1"}]),
        ],
    ) as request_mock, patch("wb_api_core.client.time.sleep") as sleep_mock:
        result = load_orders(client, "2026-10-01")

    assert result["debug"]["success"] is True
    assert request_mock.call_count == 2  # the 429 itself + exactly one retry
    assert sleep_mock.call_count == 1  # no loader-level loop on top of transport
    assert float(sleep_mock.call_args[0][0]) == 1.0
    assert result["debug"]["retry_count"] == 1
