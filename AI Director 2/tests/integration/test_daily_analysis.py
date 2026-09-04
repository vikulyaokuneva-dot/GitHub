from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.finance.contracts import FinancialComponent, FinancialComponentInput, FinancialFinality, FinancialFinalityInput, FinancialInputState, FinancialStatus
from packages.pipeline import DailyAnalysisService
from packages.products.contracts import DirectPeriodCogsInput
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import (
    ADVERTISING_PERFORMANCE_ENDPOINT,
    FINANCE_DETAIL_ENDPOINT,
    ORDERS_ENDPOINT,
    SALES_ENDPOINT,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    STOCKS_ENDPOINT,
    EndpointMetadata,
    RawObject,
    RawPayload,
    TenantAccountScope,
)
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService

DAY = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)


def _raw(*, scope: TenantAccountScope, endpoint: EndpointMetadata, suffix: str, payload: RawPayload) -> RawObject:
    metadata = endpoint
    return RawObject(
        object_id=(suffix * 64)[:64],
        scope=scope,
        endpoint=metadata,
        object_type=metadata.object_type,
        source="wildberries",
        retrieved_at=RETRIEVED_AT,
        operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()},
        payload=payload,
        schema_version=metadata.schema_version,
    )


def test_daily_analysis_runs_complete_fixture_pipeline_from_durable_raw_objects(tmp_path: Path) -> None:
    database_path = tmp_path / "analysis.sqlite3"
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="fixture_seller", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    repository = SQLiteRawObjectRepository(database_path)
    raw_objects = (
        _raw(scope=registration.scope, endpoint=ORDERS_ENDPOINT, suffix="1", payload=[{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00", "isCancel": False, "date": DAY.isoformat()}]),
        _raw(scope=registration.scope, endpoint=SALES_ENDPOINT, suffix="2", payload=[{"srid": "sale-1", "nmId": 1001, "quantity": "1", "priceWithDisc": "50.00", "date": DAY.isoformat()}]),
        _raw(scope=registration.scope, endpoint=STOCKS_ENDPOINT, suffix="3", payload={"data": [{"nmId": 1001, "quantity": "10", "inWayToClient": "1", "inWayFromClient": "2"}]}),
        _raw(
            scope=registration.scope,
            endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
            suffix="4",
            payload={
                "data": {
                    "products": [
                        {
                            "product": {"nmId": 1001, "vendorCode": "ART-1001"},
                            "statistic": {
                                "selected": {
                                    "openCount": 20,
                                    "cartCount": 4,
                                    "orderCount": 2,
                                    "buyoutCount": 1,
                                    "buyoutSum": "40.00",
                                    "currency": "RUB",
                                }
                            },
                        }
                    ]
                }
            },
        ),
        _raw(scope=registration.scope, endpoint=FINANCE_DETAIL_ENDPOINT, suffix="5", payload=[{"rrdId": "rrd-1", "rrDate": "2026-08-21", "saleDt": DAY.isoformat(), "nmId": 1001, "supplierArticle": "ART-1001", "supplierOperName": "Продажа", "docTypeName": "Продажа", "quantity": "2", "retailAmount": "1000.00", "retailPriceWithDiscRub": "600.00", "ppvzForPay": "700.00", "currency": "RUB"}]),
        _raw(scope=registration.scope, endpoint=ADVERTISING_PERFORMANCE_ENDPOINT, suffix="6", payload={"data": [{"advertId": 1, "nmId": 1001, "sum": "100.00"}, {"advertId": 1, "attributionScope": "period", "sum": "50.00"}]}),
    )
    for raw_object in raw_objects:
        repository.save(raw_object)

    result = DailyAnalysisService(accounts=accounts, raw_repository=repository, reports_root=tmp_path / "reports").run_analysis(
        account_id=registration.account_id,
        date_from=DAY,
        date_to=DAY,
        data_origin="test_fixture",
        finality=(FinancialFinalityInput(source="wildberries", source_record_id="rrd-1", operational_date=DAY, financial_date=date(2026, 8, 21), finality=FinancialFinality.FINAL, evidence_code="explicit_closed_statement"),),
        period_cogs=DirectPeriodCogsInput(scope=registration.scope, operational_date=DAY, state=FinancialInputState.PROVIDED, amount=Decimal("-300.00"), source="fixture_ledger", source_record_id="cogs-1", source_endpoint="fixture_ledger"),
        tax=SourcedTaxInput(scope=registration.scope, operational_date=DAY, financial_date=date(2026, 8, 21), state=FinancialInputState.PROVIDED, amount=Decimal("-60.00"), source="fixture_tax", source_record_id="tax-1", source_endpoint="fixture_tax"),
    )

    financial = result.pipeline.financial_flow.financial_result
    assert financial is not None
    assert result.data_origin == "test_fixture"
    assert result.status == FinancialStatus.COMPLETE
    assert financial.net_profit == Decimal("490.00")
    assert result.pipeline.operational.cohort_buyout_count.value == Decimal("1")
    assert result.pipeline.operational.sales_quantity.value == Decimal("1")
    assert result.products[0].nm_id == "1001"
    assert result.products[0].direct_advertising == Decimal("100.00")
    assert result.products[0].realized_revenue == Decimal("1000.00")
    assert result.products[0].cogs is None
    assert result.artifact.text_path.read_text(encoding="utf-8").startswith("WB Autopilot report")
    assert result.artifact.html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert result.artifact.pdf_path.read_bytes().startswith(b"%PDF")


def test_daily_analysis_marks_missing_finance_as_unavailable_without_zero_profit(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.sqlite3"
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="empty_seller", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    result = DailyAnalysisService(
        accounts=accounts,
        raw_repository=SQLiteRawObjectRepository(database_path),
        reports_root=tmp_path / "reports",
    ).run_analysis(account_id=registration.account_id, date_from=DAY, date_to=DAY, data_origin="test_fixture")

    assert result.status is None
    assert result.pipeline.financial_flow.financial_result is None
    assert result.pipeline.operational.order_quantity.value is None
    assert any("no authoritative P&L" in item for item in result.diagnostics)


class _CountingFinanceDetailTransport:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_finance_detail(self, *, operational_date: date) -> tuple[list[dict[str, object]], bytes]:
        self.calls += 1
        payload = [{
            "rrdId": "finance-1",
            "rrDate": "2026-08-21",
            "saleDt": operational_date.isoformat(),
            "nmId": 1001,
            "supplierArticle": "ART-1001",
            "supplierOperName": "sale",
            "docTypeName": "sale",
            "quantity": "1",
            "retailAmount": "100.00",
            "retailPriceWithDiscRub": "80.00",
            "ppvzForPay": "70.00",
            "currency": "RUB",
        }]
        return payload, json.dumps(payload, separators=(",", ":")).encode("utf-8")


def test_daily_analysis_ingests_finance_detail_once_and_reads_it_from_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "live.sqlite3"
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="live_seller", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    repository = SQLiteRawObjectRepository(database_path)
    transport = _CountingFinanceDetailTransport()
    analysis = DailyAnalysisService(
        accounts=accounts,
        raw_repository=repository,
        reports_root=tmp_path / "reports",
        finance_detail_ingestion=WBFinanceDetailIngestionService(repository=repository, transport=transport),
    )

    first = analysis.run_analysis(
        account_id=registration.account_id, date_from=DAY, date_to=DAY, data_origin="real_wb_data"
    )
    second = analysis.run_analysis(
        account_id=registration.account_id, date_from=DAY, date_to=DAY, data_origin="real_wb_data"
    )

    assert transport.calls == 1
    assert len(repository.list(scope=registration.scope)) == 1
    assert len(first.pipeline.finance_records) == 1
    assert first.pipeline.finance_records == second.pipeline.finance_records


def test_daily_analysis_is_repeatable_and_cannot_read_another_account_raw_objects(tmp_path: Path) -> None:
    database_path = tmp_path / "isolated.sqlite3"
    accounts = SQLiteAccountRegistrationRepository(database_path)
    service = AccountRegistrationService(accounts)
    owner = service.register_wildberries_seller(
        seller_id="owner", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL_OWNER")
    )
    other = service.register_wildberries_seller(
        seller_id="other", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL_OTHER")
    )
    repository = SQLiteRawObjectRepository(database_path)
    repository.save(
        _raw(
            scope=owner.scope,
            endpoint=SALES_ENDPOINT,
            suffix="a",
            payload=[{"srid": "sale-1", "nmId": 1001, "quantity": "1", "priceWithDisc": "20.00", "date": DAY.isoformat()}],
        )
    )
    analysis = DailyAnalysisService(accounts=accounts, raw_repository=repository, reports_root=tmp_path / "reports")

    first = analysis.run_analysis(account_id=owner.account_id, date_from=DAY, date_to=DAY, data_origin="test_fixture")
    second = analysis.run_analysis(account_id=owner.account_id, date_from=DAY, date_to=DAY, data_origin="test_fixture")
    isolated = analysis.run_analysis(account_id=other.account_id, date_from=DAY, date_to=DAY, data_origin="test_fixture")

    assert len(repository.list(scope=owner.scope)) == 1
    assert first.pipeline.report_payload == second.pipeline.report_payload
    assert first.artifact.pdf_path.read_bytes() == second.artifact.pdf_path.read_bytes()
    assert isolated.pipeline.operational.sales == ()
    assert isolated.pipeline.operational.sales_quantity.value is None


def test_daily_analysis_rejects_unknown_account_invalid_range_and_invalid_origin(tmp_path: Path) -> None:
    database_path = tmp_path / "validation.sqlite3"
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="validation", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    analysis = DailyAnalysisService(
        accounts=accounts,
        raw_repository=SQLiteRawObjectRepository(database_path),
        reports_root=tmp_path / "reports",
    )

    with pytest.raises(ValueError, match="date_from"):
        analysis.run_analysis(
            account_id=registration.account_id,
            date_from=DAY,
            date_to=date(2026, 8, 21),
            data_origin="test_fixture",
        )
    with pytest.raises(ValueError, match="data_origin"):
        analysis.run_analysis(
            account_id=registration.account_id, date_from=DAY, date_to=DAY, data_origin="unknown"
        )
    with pytest.raises(LookupError, match="not found"):
        analysis.run_analysis(
            account_id=UUID("00000000-0000-0000-0000-000000000999"),
            date_from=DAY,
            date_to=DAY,
            data_origin="test_fixture",
        )
