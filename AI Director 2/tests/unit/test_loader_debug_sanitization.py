"""Regression: loader debug/credential metadata must never enter persisted raw objects.

The RawObject credential-free validator stays the authoritative security
contract and is NOT weakened here. This suite proves the ingestion boundary
sanitizes loader transport metadata (``_loader_debug`` with
``token_present`` / ``token_env_name_used``) before RawObject creation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.wb_core.contracts import ORDERS_ENDPOINT, RawObject, TenantAccountScope
from packages.wb_core.daily_ingestion import WBDailyIngestionService, sanitize_loader_payload
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository

DAY = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)


def _register_scope(tmp_path: Path) -> TenantAccountScope:
    accounts = SQLiteAccountRegistrationRepository(tmp_path / "shared.sqlite3")
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="sanitizer_test_seller", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    return registration.scope


def _loader_payload() -> dict[str, object]:
    """Loader payload with debug block and nested credential-shaped fields."""

    return {
        "data": [{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00"}],
        "meta": {
            "token_present": True,
            "token_env_name_used": "WB_API_TOKEN",
            "keep_me": "value",
            "nested": {"authorization": "Bearer abc", "api_key": "k", "ok": 1},
            "list": [{"secret": "s", "ok": 1}],
        },
        "_loader_debug": {
            "endpoint": "orders",
            "status_code": 200,
            "token_present": True,
            "token_env_name_used": "WB_API_TOKEN",
        },
    }


class _DebugLeakingTransport:
    def load_orders(self, *, operational_date: date) -> dict[str, object]:
        return {"payload": _loader_payload(), "rows_raw": [{"srid": "order-1"}], "debug": {"token_present": True, "token_env_name_used": "WB_API_TOKEN"}}

    def load_sales(self, *, operational_date: date) -> dict[str, object]:
        return {"payload": []}

    def load_stocks(self, *, operational_date: date) -> dict[str, object]:
        return {"payload": []}

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, object]:
        return {"payload": []}

    def load_ads(self, *, operational_date: date) -> dict[str, object]:
        return {"payload": []}


def test_sanitize_loader_payload_is_deterministic_and_strips_debug_credentials() -> None:
    cleaned = sanitize_loader_payload(_loader_payload())
    assert "_loader_debug" not in cleaned
    assert "token_present" not in cleaned["meta"]
    assert "token_env_name_used" not in cleaned["meta"]
    assert cleaned["meta"]["keep_me"] == "value"
    assert "authorization" not in cleaned["meta"]["nested"]
    assert "api_key" not in cleaned["meta"]["nested"]
    assert cleaned["meta"]["nested"]["ok"] == 1
    assert "secret" not in cleaned["meta"]["list"][0]
    assert cleaned["meta"]["list"][0]["ok"] == 1
    assert sanitize_loader_payload(_loader_payload()) == cleaned


def _walk_credential_free(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert "_loader_debug" not in key
            lowered = key.lower()
            assert "token" not in lowered
            assert "authorization" not in lowered
            assert "api_key" not in lowered and "apikey" not in lowered
            assert "secret" not in lowered
            assert "credential" not in lowered
            _walk(item)
    elif isinstance(value, list):
        for item in value:
            _walk(item)


def test_ingestion_persists_raw_object_without_loader_debug_or_credentials(tmp_path: Path) -> None:
    scope = _register_scope(tmp_path)
    repository = SQLiteRawObjectRepository(tmp_path / "shared.sqlite3")
    service = WBDailyIngestionService(repository=repository, loaders=_DebugLeakingTransport())

    service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    persisted = [
        raw
        for raw in repository.list(scope=scope, endpoint_name=ORDERS_ENDPOINT.name)
        if raw.operational_date == DAY
    ]
    assert len(persisted) == 1
    raw_object: RawObject = persisted[0]
    _walk_credential_free(raw_object.payload)
    assert raw_object.payload["data"][0]["srid"] == "order-1"
    assert raw_object.payload["meta"]["keep_me"] == "value"
    assert raw_object.payload_sha256 == __import__("hashlib").sha256(raw_object.payload_bytes).hexdigest()


def test_ingestion_rerun_with_debug_payload_stays_idempotent(tmp_path: Path) -> None:
    scope = _register_scope(tmp_path)
    repository = SQLiteRawObjectRepository(tmp_path / "shared.sqlite3")
    service = WBDailyIngestionService(repository=repository, loaders=_DebugLeakingTransport())

    service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)
    service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    persisted = repository.list(scope=scope, endpoint_name=ORDERS_ENDPOINT.name)
    assert len(persisted) == 1
