"""Regression: one unavailable WB source must not poison or abort the day.

Stage 20.22 root-cause fixes locked here:

1. A loader whose debug block reports ``success: False`` (403/429/404) must
   NOT be persisted as an empty raw object — "no data" and "request failed"
   are different states, and persisting failures locks idempotency against a
   later successful refetch.
2. A transport exception for one endpoint must not prevent the remaining
   endpoints from being ingested; each failure becomes an explicit
   ``source_unavailable:<endpoint>`` diagnostic.
3. Idempotency still holds for successfully persisted sources.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from packages.accounts import (
    AccountRegistrationService,
    CredentialRef,
    SQLiteAccountRegistrationRepository,
)
from packages.wb_core.contracts import TenantAccountScope
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository

DAY = date(2026, 9, 8)
RETRIEVED_AT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _scope(tmp_path: Path) -> TenantAccountScope:
    accounts = SQLiteAccountRegistrationRepository(tmp_path / "shared.sqlite3")
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="resilience_test_seller",
        credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL"),
    )
    return registration.scope


def _orders_payload() -> list[dict[str, object]]:
    return [
        {
            "srid": "order-1",
            "nmId": 1001,
            "quantity": "1",
            "priceWithDisc": "100.00",
            "isCancel": False,
            "date": DAY.isoformat(),
        }
    ]


class _PartialFailureTransport:
    """funnel raises; stocks reports failure in debug; the rest succeed."""

    def __init__(self) -> None:
        self.load_orders_calls = 0

    def load_orders(self, *, operational_date: date) -> dict[str, object]:
        self.load_orders_calls += 1
        return {"payload": _orders_payload()}

    def load_sales(self, *, operational_date: date) -> dict[str, object]:
        return {"payload": []}

    def load_stocks(self, *, operational_date: date) -> dict[str, object]:
        return {
            "rows_raw": [],
            "debug": {
                "success": False,
                "status_code": 403,
                "error_text": "403: token does not satisfy additional requirements",
            },
        }

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, object]:
        raise RuntimeError("sales_funnel_products WB request failed with status 403")

    def load_ads(self, *, operational_date: date) -> dict[str, object]:
        return {
            "rows_raw": [
                {"date": operational_date.isoformat(), "sku": "1001", "sum": "5.00"}
            ]
        }


class _AllFailingTransport:
    def load_orders(self, *, operational_date: date) -> dict[str, object]:
        raise RuntimeError("orders WB request failed with status 429")

    def load_sales(self, *, operational_date: date) -> dict[str, object]:
        raise RuntimeError("sales WB request failed with status 429")

    def load_stocks(self, *, operational_date: date) -> dict[str, object]:
        raise RuntimeError("stocks WB request failed with status 403")

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, object]:
        raise RuntimeError("sales_funnel_products WB request failed with status 403")

    def load_ads(self, *, operational_date: date) -> dict[str, object]:
        raise RuntimeError("advertising_performance WB request failed with status 429")


def test_failed_sources_degrade_to_diagnostics_and_never_persist_as_empty(tmp_path: Path) -> None:
    scope = _scope(tmp_path)
    repository = SQLiteRawObjectRepository(tmp_path / "shared.sqlite3")
    transport = _PartialFailureTransport()
    service = WBDailyIngestionService(repository=repository, loaders=transport)

    diagnostics = service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    joined = "\n".join(diagnostics)
    assert "source_unavailable:stocks" in joined
    assert "403" in joined
    assert "source_unavailable:sales_funnel_products" in joined

    # Successful sources are persisted...
    assert len(repository.list(scope=scope, endpoint_name="orders")) == 1
    assert len(repository.list(scope=scope, endpoint_name="sales")) == 1
    assert len(repository.list(scope=scope, endpoint_name="advertising_performance")) == 1

    # ...and failed sources left no raw object behind (not even an empty one).
    assert repository.list(scope=scope, endpoint_name="stocks") == ()
    assert repository.list(scope=scope, endpoint_name="sales_funnel_products") == ()


def test_retry_after_failure_refetches_only_unpersisted_sources(tmp_path: Path) -> None:
    scope = _scope(tmp_path)
    repository = SQLiteRawObjectRepository(tmp_path / "shared.sqlite3")
    transport = _PartialFailureTransport()
    service = WBDailyIngestionService(repository=repository, loaders=transport)

    first = service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)
    assert first  # diagnostics for the failed sources
    assert transport.load_orders_calls == 1

    second = service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    # Orders were already persisted: the idempotency guard must not refetch.
    assert transport.load_orders_calls == 1
    # Stocks/funnel never persisted, so they are attempted again (still failing).
    assert "source_unavailable:stocks" in "\n".join(second)
    assert "source_unavailable:sales_funnel_products" in "\n".join(second)


def test_all_sources_failing_persists_nothing_and_reports_every_source(tmp_path: Path) -> None:
    scope = _scope(tmp_path)
    repository = SQLiteRawObjectRepository(tmp_path / "shared.sqlite3")
    service = WBDailyIngestionService(repository=repository, loaders=_AllFailingTransport())

    diagnostics = service.ingest(scope=scope, operational_date=DAY, retrieved_at=RETRIEVED_AT)

    assert len(diagnostics) == 5
    assert repository.list(scope=scope) == ()
