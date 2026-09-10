"""Minimal regression test for STAGE 20.17 RuntimeError handling at /audit endpoint.

Verifies that a RuntimeError raised by the audit boundary (e.g. a WB 429 when
no source could be ingested at all) is mapped to a controlled HTTP 503 with a
``transport/upstream error`` detail, while lookup/contract errors stay 400.
No WB request is performed here: the auditor is a raising stub.
"""

from __future__ import annotations

from typing import cast
from uuid import uuid4

from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.common.settings import Settings
from packages.pipeline.audit import CabinetAuditor


def _settings() -> Settings:
    return Settings(service_name="test-api", environment="test", version="0.1.0-test")


class _RaisingAuditor:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def audit(self, **_kwargs: object) -> None:
        raise self._error


def _client(error: Exception) -> TestClient:
    return TestClient(
        create_app(settings=_settings(), audit_service=cast(CabinetAuditor, _RaisingAuditor(error)))
    )


def test_audit_maps_runtime_error_to_controlled_503() -> None:
    client = _client(RuntimeError("orders WB request failed with status 429"))

    response = client.get(f"/audit/{uuid4()}?date=2026-09-08")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail.startswith("transport/upstream error")
    assert "429" in detail


def test_audit_maps_unknown_account_to_400() -> None:
    client = _client(LookupError("registered account not found"))

    response = client.get(f"/audit/{uuid4()}?date=2026-09-08")

    assert response.status_code == 400


def test_audit_maps_invalid_data_origin_to_400() -> None:
    client = _client(ValueError("data_origin must be real_wb_data or test_fixture"))

    response = client.get(f"/audit/{uuid4()}?date=2026-09-08&data_origin=nonsense")

    assert response.status_code == 400
