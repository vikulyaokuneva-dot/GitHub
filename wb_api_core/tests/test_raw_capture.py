from __future__ import annotations

import hashlib
import json
from importlib import import_module
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from wb_api_core.client import WBApiClient
from wb_api_core.raw_capture import RawCaptureError, RawCaptureWriter


def _response(payload: object) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = payload
    return response


def _request(client: WBApiClient) -> dict[str, object]:
    return client.request_json(
        endpoint_name="orders",
        path="/api/v1/supplier/orders",
        params={"dateFrom": "2026-08-25", "flag": 0},
    )


def _writer(destination: Path) -> RawCaptureWriter:
    return RawCaptureWriter(
        destination=destination,
        capture_id="wb-capture-001",
        tenant_id="tenant-001",
        account_id="account-001",
        operational_date="2026-08-25",
        clock=lambda: datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc),
    )


def test_capture_is_disabled_by_default_and_preserves_the_existing_response(tmp_path: Path) -> None:
    payload = {"data": [{"nmId": 1001}]}
    client = WBApiClient(token="test-token")

    with patch("wb_api_core.client.requests.request", return_value=_response(payload)):
        result = _request(client)

    assert result["success"] is True
    assert result["payload"] is payload
    assert not list(tmp_path.iterdir())


def test_enabled_capture_writes_exact_raw_payload_and_returns_it_unchanged(tmp_path: Path) -> None:
    payload = {"data": [{"nmId": 1001, "nested": {"value": "raw"}}]}
    client = WBApiClient(token="test-token", capture_writer=_writer(tmp_path))

    with patch("wb_api_core.client.requests.request", return_value=_response(payload)):
        result = _request(client)

    capture_directory = tmp_path / "wb-capture-001"
    raw_path = capture_directory / "raw" / "0001_orders.json"
    manifest = json.loads((capture_directory / "manifest.json").read_text(encoding="utf-8"))
    raw_bytes = raw_path.read_bytes()
    assert result["payload"] is payload
    assert payload == {"data": [{"nmId": 1001, "nested": {"value": "raw"}}]}
    assert json.loads(raw_bytes) == payload
    assert manifest["scope"] == {"tenant_id": "tenant-001", "account_id": "account-001"}
    assert manifest["objects"][0]["retrieved_at"] == "2026-08-25T10:30:00Z"
    assert manifest["objects"][0]["operational_date"] == "2026-08-25"
    assert manifest["objects"][0]["http"] == {"status_code": 200}
    assert manifest["objects"][0]["sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert manifest["objects"][0]["byte_length"] == len(raw_bytes)
    assert "authorization" not in (capture_directory / "manifest.json").read_text(encoding="utf-8").lower()


@pytest.mark.parametrize(
    "payload",
    [
        {"nested": {"apiToken": "not-stored"}},
        {"nested": {"authorization": "Bearer not-stored"}},
    ],
)
def test_capture_rejects_credential_like_payload_before_writing(tmp_path: Path, payload: object) -> None:
    client = WBApiClient(token="test-token", capture_writer=_writer(tmp_path))

    with patch("wb_api_core.client.requests.request", return_value=_response(payload)):
        with pytest.raises(RawCaptureError, match="raw capture failed"):
            _request(client)

    assert not (tmp_path / "wb-capture-001").exists()


def test_capture_rejects_credential_like_request_metadata_before_writing(tmp_path: Path) -> None:
    client = WBApiClient(token="test-token", capture_writer=_writer(tmp_path))

    with patch("wb_api_core.client.requests.request", return_value=_response({"data": []})):
        with pytest.raises(RawCaptureError, match="raw capture failed"):
            client.request_json(
                endpoint_name="orders",
                path="/api/v1/supplier/orders",
                params={"authorization": "Bearer not-stored"},
            )

    assert not (tmp_path / "wb-capture-001").exists()


def test_capture_manifest_is_deterministic_for_identical_capture_inputs(tmp_path: Path) -> None:
    payload = {"data": [{"nmId": 1001}]}
    manifests: list[bytes] = []
    raw_payloads: list[bytes] = []

    for destination in (tmp_path / "first", tmp_path / "second"):
        client = WBApiClient(token="test-token", capture_writer=_writer(destination))
        with patch("wb_api_core.client.requests.request", return_value=_response(payload)):
            _request(client)
        capture_directory = destination / "wb-capture-001"
        manifests.append((capture_directory / "manifest.json").read_bytes())
        raw_payloads.append((capture_directory / "raw" / "0001_orders.json").read_bytes())

    assert manifests[0] == manifests[1]
    assert raw_payloads[0] == raw_payloads[1]


def test_capture_failure_is_loud_and_does_not_retry_or_return_a_changed_result() -> None:
    class FailingWriter:
        def capture(self, **_: object) -> None:
            raise OSError("disk is unavailable")

    client = WBApiClient(token="test-token", capture_writer=FailingWriter())
    with patch("wb_api_core.client.requests.request", return_value=_response({"data": []})) as request_mock:
        with pytest.raises(RawCaptureError, match="raw capture failed"):
            _request(client)

    request_mock.assert_called_once()


def test_capture_hook_never_invokes_normalization_or_finance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    normalize_module = import_module("wb_api_core.normalize")
    reconcile_module = import_module("wb_api_core.reconcile")

    monkeypatch.setattr(normalize_module, "normalize_bundle", lambda *_: pytest.fail("normalization must not run"))
    monkeypatch.setattr(reconcile_module, "reconcile_bundle", lambda *_: pytest.fail("reconciliation must not run"))
    client = WBApiClient(token="test-token", capture_writer=_writer(tmp_path))

    with patch("wb_api_core.client.requests.request", return_value=_response({"data": []})):
        result = _request(client)

    assert result["success"] is True
