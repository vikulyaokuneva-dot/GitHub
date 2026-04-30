from __future__ import annotations

from unittest.mock import MagicMock, patch

from wb_api_core.client import WBApiClient


def _response(status_code: int, *, headers: dict[str, str] | None = None, payload: object | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = "too many requests" if status_code == 429 else ""
    response.json.return_value = payload if payload is not None else {"ok": True}
    return response


def _retry_policy(*, cap_delay_seconds: float = 30.0, max_attempts: int = 2) -> dict:
    return {
        "retryable_statuses": (429,),
        "max_attempts": max_attempts,
        "base_delay_seconds": 1.0,
        "cap_delay_seconds": cap_delay_seconds,
        "jitter_ratio": 0.0,
        "max_retry_window_seconds": 120.0,
    }


def _request_with_first_429(headers: dict[str, str], *, cap_delay_seconds: float = 30.0) -> tuple[dict, MagicMock]:
    client = WBApiClient(token="token")
    with patch(
        "wb_api_core.client.requests.request",
        side_effect=[_response(429, headers=headers), _response(200)],
    ):
        with patch("wb_api_core.client.time.sleep") as sleep_mock:
            response = client.request_json(
                endpoint_name="orders",
                path="/api/v1/supplier/orders",
                retry_policy=_retry_policy(cap_delay_seconds=cap_delay_seconds),
            )
    return response, sleep_mock


def test_retry_after_header_is_used_as_retry_delay() -> None:
    response, sleep_mock = _request_with_first_429({"Retry-After": "7"})

    assert response["success"] is True
    sleep_mock.assert_called_once_with(7.0)
    assert response["retry_delays"] == [7.0]
    assert response["retry_after"] == "7"
    assert response["rate_limit_delay_seconds"] == 7.0


def test_x_ratelimit_retry_is_used_when_retry_after_is_missing() -> None:
    response, sleep_mock = _request_with_first_429({"X-Ratelimit-Retry": "8"})

    assert response["success"] is True
    sleep_mock.assert_called_once_with(8.0)
    assert response["retry_delays"] == [8.0]
    assert response["x_ratelimit_retry"] == "8"
    assert response["rate_limit_delay_seconds"] == 8.0


def test_x_ratelimit_reset_timestamp_is_used_when_other_headers_are_missing() -> None:
    with patch("wb_api_core.client.time.time", return_value=4_102_444_800.0):
        response, sleep_mock = _request_with_first_429({"X-Ratelimit-Reset": "4102444812"})

    assert response["success"] is True
    sleep_mock.assert_called_once_with(12.0)
    assert response["retry_delays"] == [12.0]
    assert response["x_ratelimit_reset"] == "4102444812"
    assert response["rate_limit_delay_seconds"] == 12.0


def test_rate_limit_header_delay_is_capped() -> None:
    response, sleep_mock = _request_with_first_429({"Retry-After": "99"}, cap_delay_seconds=10.0)

    assert response["success"] is True
    sleep_mock.assert_called_once_with(10.0)
    assert response["retry_delays"] == [10.0]
    assert response["rate_limit_delay_seconds"] == 10.0


def test_failed_429_response_contains_rate_limit_debug_fields() -> None:
    client = WBApiClient(token="token")
    headers = {
        "Retry-After": "4",
        "X-Ratelimit-Retry": "5",
        "X-Ratelimit-Reset": "4102444812",
        "X-Ratelimit-Remaining": "0",
    }

    with patch("wb_api_core.client.requests.request", return_value=_response(429, headers=headers)):
        response = client.request_json(
            endpoint_name="stocks",
            path="/api/v1/supplier/stocks",
            retry_policy=_retry_policy(max_attempts=1),
        )

    assert response["success"] is False
    assert response["status_code"] == 429
    assert response["retry_after"] == "4"
    assert response["x_ratelimit_retry"] == "5"
    assert response["x_ratelimit_reset"] == "4102444812"
    assert response["x_ratelimit_remaining"] == "0"
    assert "retry_after=4" in response["error_text"]
    assert "x_ratelimit_remaining=0" in response["final_failure_reason"]
