"""Integration: audit survives partially unavailable WB sources and refuses
a day where no source could be ingested at all.

Guards the STAGE 20.22 contract:
- partial outage  -> audit completes, ingestion_status is marked degraded,
  every unavailable source appears in diagnostics, available sources flow
  through the kernel unchanged;
- total outage    -> RuntimeError (API maps it to 503), never a fake
  "everything is no data" success.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from packages.accounts import (
    AccountRegistrationService,
    CredentialRef,
    SQLiteAccountRegistrationRepository,
)
from packages.pipeline import CabinetAuditor, DailyAnalysisService
from packages.wb_core.contracts import RawObjectType
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository

DAY = date(2026, 9, 8)


class _PartiallyFailingLoaders:
    """orders/sales/advertising succeed; stocks/funnel are unavailable."""

    def __init__(self) -> None:
        self.call_counts: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.call_counts[name] = self.call_counts.get(name, 0) + 1

    def load_orders(self, *, operational_date: date) -> dict[str, object]:
        self._count("orders")
        return {
            "payload": [
                {
                    "srid": "order-1",
                    "nmId": 1001,
                    "quantity": "1",
                    "priceWithDisc": "100.00",
                    "isCancel": False,
                    "date": operational_date.isoformat(),
                }
            ]
        }

    def load_sales(self, *, operational_date: date) -> dict[str, object]:
        self._count("sales")
        return {"payload": []}

    def load_stocks(self, *, operational_date: date) -> dict[str, object]:
        self._count("stocks")
        return {
            "rows_raw": [],
            "debug": {
                "success": False,
                "status_code": 403,
                "error_text": "403: token does not satisfy additional requirements",
            },
        }

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, object]:
        self._count("funnel")
        raise RuntimeError("sales_funnel_products WB request failed with status 403")

    def load_ads(self, *, operational_date: date) -> dict[str, object]:
        self._count("ads")
        return {
            "rows_raw": [
                {"date": operational_date.isoformat(), "sku": "1001", "sum": "10.00"}
            ]
        }


class _AllFailingLoaders(_PartiallyFailingLoaders):
    def load_orders(self, *, operational_date: date) -> dict[str, object]:
        self._count("orders")
        raise RuntimeError("orders WB request failed with status 429")

    def load_sales(self, *, operational_date: date) -> dict[str, object]:
        self._count("sales")
        raise RuntimeError("sales WB request failed with status 429")

    def load_ads(self, *, operational_date: date) -> dict[str, object]:
        self._count("ads")
        raise RuntimeError("advertising_performance WB request failed with status 429")


class _WorkingFinanceTransport:
    def fetch_finance_detail(self, *, operational_date: date) -> tuple[list[dict[str, object]], bytes]:
        import json

        payload = [
            {
                "rrdId": "finance-1",
                "rrDate": "2026-09-09",
                "saleDt": operational_date.isoformat(),
                "nmId": 1001,
                "supplierArticle": "ART-1001",
                "supplierOperName": "Продажа",
                "docTypeName": "Продажа",
                "quantity": "1",
                "retailAmount": "100.00",
                "retailPriceWithDiscRub": "80.00",
                "ppvzForPay": "70.00",
                "currency": "RUB",
            }
        ]
        return payload, json.dumps(payload, separators=(",", ":")).encode("utf-8")


class _FailingFinanceTransport:
    def fetch_finance_detail(self, *, operational_date: date) -> tuple[list[dict[str, object]], bytes]:
        raise RuntimeError("finance_detail WB request failed with status 429")


def _build(database_path: Path, loaders: Any, finance_transport: Any) -> tuple[CabinetAuditor, Any]:
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="degraded_seller",
        credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL"),
    )
    repository = SQLiteRawObjectRepository(database_path)
    daily = WBDailyIngestionService(repository=repository, loaders=loaders)
    finance = WBFinanceDetailIngestionService(repository=repository, transport=finance_transport)
    analysis = DailyAnalysisService(
        accounts=accounts,
        raw_repository=repository,
        reports_root=database_path.parent / "reports",
        daily_ingestion=daily,
        finance_detail_ingestion=finance,
    )
    auditor = CabinetAuditor(
        accounts=accounts,
        raw_repository=repository,
        analysis_service=analysis,
        daily_ingestion=daily,
        finance_detail_ingestion=finance,
    )
    return auditor, registration


def test_audit_completes_with_degraded_sources_and_explicit_diagnostics(tmp_path: Path) -> None:
    loaders = _PartiallyFailingLoaders()
    auditor, registration = _build(
        tmp_path / "degraded.sqlite3", loaders, _WorkingFinanceTransport()
    )

    result = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
    )

    assert result.ingestion_status == "ingested:daily+finance_detail+degraded"
    joined = "\n".join(result.diagnostics)
    assert "source_unavailable:stocks" in joined
    assert "source_unavailable:sales_funnel_products" in joined
    # The audit owns the ingestion boundary: the analysis must not re-request
    # WB sources already obtained moments earlier (one call per source).
    assert loaders.call_counts == {"orders": 1, "sales": 1, "stocks": 1, "funnel": 1, "ads": 1}
    # Each unavailable source is reported exactly once.
    assert joined.count("source_unavailable:stocks") == 1
    assert joined.count("source_unavailable:sales_funnel_products") == 1
    # Available sources still reach the audit day unchanged.
    assert result.raw_references.object_ids(RawObjectType.ORDERS)
    assert result.raw_references.object_ids(RawObjectType.FINANCE_DETAIL)
    # Failed sources leave no raw behind.
    assert not result.raw_references.object_ids(RawObjectType.STOCKS)
    assert not result.raw_references.object_ids(RawObjectType.SALES_FUNNEL_PRODUCTS)


def test_audit_refuses_day_when_no_source_can_be_ingested(tmp_path: Path) -> None:
    auditor, registration = _build(
        tmp_path / "outage.sqlite3", _AllFailingLoaders(), _FailingFinanceTransport()
    )

    with pytest.raises(RuntimeError, match="no WB source could be ingested"):
        auditor.audit(
            account_id=registration.account_id,
            operational_date=DAY,
            data_origin="real_wb_data",
        )
