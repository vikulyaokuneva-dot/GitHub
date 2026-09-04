from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import pytest

from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.persistence.sqlite import apply_migrations, connect, rollback_last_migration
from packages.wb_core.contracts import (
    DuplicateRawObjectError,
    RawObject,
    RawObjectNotFoundError,
    RawObjectType,
    ORDERS_ENDPOINT,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    TenantAccountScope,
)
from packages.wb_core.ingestion import WBSalesFunnelIngestionService
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService
from packages.wb_core.operational_ingestion import WBOrdersIngestionService, WBSalesIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository


def _registration_service(database_path: Path) -> AccountRegistrationService:
    return AccountRegistrationService(SQLiteAccountRegistrationRepository(database_path))


def _raw(scope: TenantAccountScope) -> RawObject:
    return RawObject(
        object_id="a" * 64,
        scope=scope,
        endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
        object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
        source="wildberries",
        retrieved_at=datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
        operational_date=date(2026, 8, 20),
        request_scope={"offset": 0, "limit": 1000},
        payload={"data": {"products": []}},
        schema_version="analytics-v3",
    )


def test_registration_creates_stable_internal_uuid_scope_and_retains_external_seller_id(tmp_path: Path) -> None:
    service = _registration_service(tmp_path / "foundation.sqlite3")
    first = service.register_wildberries_seller(seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN"))
    second = service.register_wildberries_seller(seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN"))

    assert first == second
    assert first.seller_id == "seller_001"
    assert isinstance(first.tenant_id, UUID)
    assert isinstance(first.account_id, UUID)
    assert first.tenant_id != first.account_id
    assert str(first.tenant_id) != first.seller_id
    assert first.credential_ref.reference == "WB_API_TOKEN"
    assert "token-value" not in first.model_dump_json()


def test_credential_reference_rejects_secret_value() -> None:
    with pytest.raises(ValueError):
        CredentialRef(reference="Bearer token-value")


def test_sqlite_migration_has_a_reversible_rollback(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    apply_migrations(database_path)

    def tables() -> set[str]:
        with connect(database_path) as connection:
            return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}

    assert {
        "raw_objects",
        "raw_object_payload_bytes",
        "product_cost_settings",
        "tax_rate_settings",
        "period_finality_confirmations",
    } <= tables()

    # version 3: seller financial parameters roll back without touching raw data
    assert rollback_last_migration(database_path) is True
    assert {
        "product_cost_settings",
        "tax_rate_settings",
        "period_finality_confirmations",
    }.isdisjoint(tables())
    assert {"raw_objects", "raw_object_payload_bytes"} <= tables()

    # version 2
    assert rollback_last_migration(database_path) is True
    assert "raw_object_payload_bytes" not in tables()
    assert "raw_objects" in tables()

    # version 1
    assert rollback_last_migration(database_path) is True
    assert "raw_objects" not in tables()

    assert rollback_last_migration(database_path) is False


def test_durable_raw_repository_persists_scope_isolates_and_reopens(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    service = _registration_service(database_path)
    owner = service.register_wildberries_seller(seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN"))
    other = service.register_wildberries_seller(seller_id="seller_002", credential_ref=CredentialRef(reference="WB_API_TOKEN_2"))
    repository = SQLiteRawObjectRepository(database_path)
    raw_object = _raw(owner.scope)

    repository.save(raw_object)
    reloaded = SQLiteRawObjectRepository(database_path).get(scope=owner.scope, object_id=raw_object.object_id)

    assert reloaded.object_id == raw_object.object_id
    assert reloaded.scope == raw_object.scope
    assert reloaded.endpoint == raw_object.endpoint
    assert reloaded.operational_date == raw_object.operational_date
    assert reloaded.request_scope == raw_object.request_scope
    assert reloaded.payload == raw_object.payload
    assert reloaded.payload_bytes == raw_object.payload_bytes
    assert reloaded.payload["data"]["products"] == ()
    assert repository.list(scope=other.scope) == ()
    with pytest.raises(RawObjectNotFoundError):
        repository.get(scope=other.scope, object_id=raw_object.object_id)
    with pytest.raises(DuplicateRawObjectError):
        repository.save(raw_object)


def test_raw_repository_enforces_scope_isolation_for_two_accounts_after_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    service = _registration_service(database_path)
    account_a = service.register_wildberries_seller(
        seller_id="seller_a", credential_ref=CredentialRef(reference="WB_API_TOKEN_A")
    )
    account_b = service.register_wildberries_seller(
        seller_id="seller_b", credential_ref=CredentialRef(reference="WB_API_TOKEN_B")
    )
    repository = SQLiteRawObjectRepository(database_path)
    object_a = _raw(account_a.scope)
    object_b = _raw(account_b.scope).model_copy(update={"object_id": "b" * 64, "scope": account_b.scope})
    repository.save(object_a)
    repository.save(object_b)

    reopened = SQLiteRawObjectRepository(database_path)
    assert [item.object_id for item in reopened.list(scope=account_a.scope)] == [object_a.object_id]
    assert [item.object_id for item in reopened.list(scope=account_b.scope)] == [object_b.object_id]
    with pytest.raises(RawObjectNotFoundError):
        reopened.get(scope=account_a.scope, object_id=object_b.object_id)
    with pytest.raises(RawObjectNotFoundError):
        reopened.get(scope=account_b.scope, object_id=object_a.object_id)


class _FakeSalesFunnelTransport:
    def fetch_sales_funnel_products(self, *, operational_date: date) -> Mapping[str, Any]:
        assert operational_date == date(2026, 8, 20)
        return {
            "data": {
                "products": [
                    {
                        "product": {"nmId": 1001, "vendorCode": "ART-1001"},
                        "statistic": {"selected": {"orderCount": 2, "orderSum": "123.45", "currency": "RUB"}},
                    }
                ]
            }
        }


def test_ingestion_reads_durable_raw_object_before_canonical_normalization(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    registration = _registration_service(database_path).register_wildberries_seller(
        seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN")
    )
    repository = SQLiteRawObjectRepository(database_path)
    service = WBSalesFunnelIngestionService(repository=repository, transport=_FakeSalesFunnelTransport())

    records = service.ingest(
        scope=registration.scope,
        operational_date=date(2026, 8, 20),
        retrieved_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )

    stored = repository.list(scope=registration.scope)
    assert len(records) == 1
    assert records[0].nm_id == "1001"
    assert records[0].source_amount is not None
    assert len(stored) == 1
    assert stored[0].payload["data"]["products"][0]["product"]["nmId"] == 1001


def test_array_root_preserves_exact_bytes_hash_and_immutability_after_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    registration = _registration_service(database_path).register_wildberries_seller(
        seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN")
    )
    raw_bytes = b'[{"srid":"order-1","nmId":1001,"quantity":"2","priceWithDisc":"123.45","isCancel":false,"date":"2026-08-20"}]'
    raw_object = RawObject(
        object_id="c" * 64,
        scope=registration.scope,
        endpoint=ORDERS_ENDPOINT,
        object_type=RawObjectType.ORDERS,
        source="wildberries",
        retrieved_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        operational_date=date(2026, 8, 20),
        request_scope={"dateFrom": "2026-08-20", "flag": 0},
        payload=[
            {
                "srid": "order-1",
                "nmId": 1001,
                "quantity": "2",
                "priceWithDisc": "123.45",
                "isCancel": False,
                "date": "2026-08-20",
            }
        ],
        raw_payload_bytes=raw_bytes,
        schema_version=ORDERS_ENDPOINT.schema_version,
    )
    repository = SQLiteRawObjectRepository(database_path)
    repository.save(raw_object)

    reloaded = SQLiteRawObjectRepository(database_path).get(scope=registration.scope, object_id=raw_object.object_id)
    assert reloaded.payload_bytes == raw_bytes
    assert reloaded.payload_sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert reloaded.payload[0]["srid"] == "order-1"
    with pytest.raises(TypeError):
        reloaded.payload[0] = {}  # type: ignore[index]


def test_array_root_rejects_nested_credentials() -> None:
    with pytest.raises(ValueError, match="credential-like"):
        RawObject(
            object_id="d" * 64,
            scope=TenantAccountScope(tenant_id=UUID("00000000-0000-0000-0000-000000000001"), account_id=UUID("00000000-0000-0000-0000-000000000002")),
            endpoint=ORDERS_ENDPOINT,
            object_type=RawObjectType.ORDERS,
            source="wildberries",
            retrieved_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
            operational_date=date(2026, 8, 20),
            request_scope={"dateFrom": "2026-08-20", "flag": 0},
            payload=[{"nested": {"Authorization": "Bearer forbidden"}}],
            schema_version=ORDERS_ENDPOINT.schema_version,
        )


class _FakeOrdersTransport:
    def fetch_orders(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        assert operational_date == date(2026, 8, 20)
        raw_bytes = b'[{"srid":"order-1","nmId":1001,"supplierArticle":"ART-1001","quantity":"2","priceWithDisc":"123.45","isCancel":false,"date":"2026-08-20"}]'
        return [
            {
                "srid": "order-1",
                "nmId": 1001,
                "supplierArticle": "ART-1001",
                "quantity": "2",
                "priceWithDisc": "123.45",
                "isCancel": False,
                "date": "2026-08-20",
            }
        ], raw_bytes


def test_orders_array_ingestion_normalizes_untouched_raw_array_after_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    registration = _registration_service(database_path).register_wildberries_seller(
        seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN")
    )
    repository = SQLiteRawObjectRepository(database_path)
    records = WBOrdersIngestionService(repository=repository, transport=_FakeOrdersTransport()).ingest(
        scope=registration.scope,
        operational_date=date(2026, 8, 20),
        retrieved_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )

    reloaded = SQLiteRawObjectRepository(database_path).list(scope=registration.scope)
    assert len(records) == 1
    assert records[0].source_event_id == "order-1"
    assert records[0].source_metadata.source_object_id == reloaded[0].object_id
    assert isinstance(reloaded[0].payload, tuple)
    assert not isinstance(reloaded[0].payload, dict)


class _FakeSalesTransport:
    def fetch_sales(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        assert operational_date == date(2026, 8, 20)
        raw_bytes = b'[{"srid":"sale-1","nmId":1001,"supplierArticle":"ART-1001","quantity":"1","priceWithDisc":"50.00","date":"2026-08-20"}]'
        return [
            {
                "srid": "sale-1",
                "nmId": 1001,
                "supplierArticle": "ART-1001",
                "quantity": "1",
                "priceWithDisc": "50.00",
                "date": "2026-08-20",
            }
        ], raw_bytes


def test_sales_array_ingestion_normalizes_untouched_raw_array_after_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    registration = _registration_service(database_path).register_wildberries_seller(
        seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN")
    )
    repository = SQLiteRawObjectRepository(database_path)
    records = WBSalesIngestionService(repository=repository, transport=_FakeSalesTransport()).ingest(
        scope=registration.scope,
        operational_date=date(2026, 8, 20),
        retrieved_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )

    reloaded = SQLiteRawObjectRepository(database_path).list(scope=registration.scope)
    assert len(records) == 1
    assert records[0].source_event_id == "sale-1"
    assert records[0].source_metadata.source_object_id == reloaded[0].object_id
    assert isinstance(reloaded[0].payload, tuple)
    assert reloaded[0].payload_bytes.startswith(b"[")


class _FakeFinanceDetailTransport:
    def fetch_finance_detail(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        assert operational_date == date(2026, 8, 20)
        raw_bytes = (
            b'[{"rrdId":"finance-1","rrDate":"2026-08-21","saleDt":"2026-08-20",'
            b'"nmId":1001,"supplierArticle":"ART-1001","supplierOperName":"sale",'
            b'"docTypeName":"sale","quantity":"1","retailAmount":"100.00",'
            b'"retailPriceWithDiscRub":"80.00","ppvzForPay":"70.00","currency":"RUB"}]'
        )
        return [
            {
                "rrdId": "finance-1",
                "rrDate": "2026-08-21",
                "saleDt": "2026-08-20",
                "nmId": 1001,
                "supplierArticle": "ART-1001",
                "supplierOperName": "sale",
                "docTypeName": "sale",
                "quantity": "1",
                "retailAmount": "100.00",
                "retailPriceWithDiscRub": "80.00",
                "ppvzForPay": "70.00",
                "currency": "RUB",
            }
        ], raw_bytes


def test_finance_detail_ingestion_reopens_exact_raw_before_existing_normalization(tmp_path: Path) -> None:
    database_path = tmp_path / "foundation.sqlite3"
    registration = _registration_service(database_path).register_wildberries_seller(
        seller_id="seller_001", credential_ref=CredentialRef(reference="WB_API_TOKEN")
    )
    repository = SQLiteRawObjectRepository(database_path)
    records = WBFinanceDetailIngestionService(repository=repository, transport=_FakeFinanceDetailTransport()).ingest(
        scope=registration.scope,
        operational_date=date(2026, 8, 20),
        retrieved_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )

    reloaded = SQLiteRawObjectRepository(database_path).list(scope=registration.scope)
    assert len(records) == 1
    assert records[0].source_record_id == "finance-1"
    assert records[0].retail_amount is not None
    assert reloaded[0].payload_bytes == _FakeFinanceDetailTransport().fetch_finance_detail(
        operational_date=date(2026, 8, 20)
    )[1]
