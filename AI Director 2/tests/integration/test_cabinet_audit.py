"""Integration tests for the MVP cabinet daily audit orchestrator."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.finance.contracts import (
    FinancialComponent,
    FinancialComponentInput,
    FinancialComponentStatus,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialInputState,
    FinancialStatus,
)
from packages.pipeline import CabinetAuditor, DailyAnalysisService, resolve_operational_date
from packages.products.contracts import DirectPeriodCogsInput
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import RawObjectType
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository

DAY = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Counting fakes: prove fetch happens exactly once and is then idempotent.
# ---------------------------------------------------------------------------


class _CountingDailyLoadersTransport:
    """Loader-shaped transport that counts every legacy loader call."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def load_orders(self, *, operational_date: date) -> dict[str, object]:
        self._called("load_orders")
        return {"payload": [{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00", "isCancel": False, "date": operational_date.isoformat()}]}

    def load_sales(self, *, operational_date: date) -> dict[str, object]:
        self._called("load_sales")
        return {"payload": [{"srid": "sale-1", "nmId": 1001, "quantity": "1", "priceWithDisc": "50.00", "date": operational_date.isoformat()}]}

    def load_stocks(self, *, operational_date: date) -> dict[str, object]:
        self._called("load_stocks")
        return {"payload": {"data": [{"nmId": 1001, "quantity": "10", "inWayToClient": "1", "inWayFromClient": "2"}]}}

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, object]:
        self._called("load_cabinet_commerce")
        return {
            "payload": {
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
            }
        }

    def load_ads(self, *, operational_date: date) -> dict[str, object]:
        self._called("load_ads")
        return {"payload": {"data": [{"advertId": 1, "nmId": 1001, "sum": "100.00"}, {"advertId": 1, "attributionScope": "period", "sum": "50.00"}]}}


class _CountingFinanceDetailTransport:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_finance_detail(self, *, operational_date: date) -> tuple[list[dict[str, object]], bytes]:
        self.calls += 1
        payload = [
            {
                "rrdId": "finance-1",
                "rrDate": "2026-08-21",
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


# ---------------------------------------------------------------------------
# Shared fixture wiring
# ---------------------------------------------------------------------------


def _register(database_path: Path, seller_id: str):
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id=seller_id, credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    return accounts, registration


def _build_auditor(
    database_path: Path,
    *,
    daily_transport: _CountingDailyLoadersTransport | None = None,
    finance_transport: _CountingFinanceDetailTransport | None = None,
) -> tuple[CabinetAuditor, SQLiteRawObjectRepository]:
    accounts, _ = _register(database_path, "audit_seller")
    repository = SQLiteRawObjectRepository(database_path)
    daily_ingestion = (
        WBDailyIngestionService(repository=repository, loaders=daily_transport)
        if daily_transport is not None
        else None
    )
    finance_detail_ingestion = (
        WBFinanceDetailIngestionService(repository=repository, transport=finance_transport)
        if finance_transport is not None
        else None
    )
    # Production wiring shares the same ingestion boundaries between the
    # orchestrator and the analysis service; ingestion is idempotent by raw
    # identity, so the second call never refetches.
    analysis = DailyAnalysisService(
        accounts=accounts,
        raw_repository=repository,
        reports_root=database_path.parent / "reports",
        daily_ingestion=daily_ingestion,
        finance_detail_ingestion=finance_detail_ingestion,
    )
    return (
        CabinetAuditor(
            accounts=accounts,
            raw_repository=repository,
            analysis_service=analysis,
            daily_ingestion=daily_ingestion,
            finance_detail_ingestion=finance_detail_ingestion,
        ),
        repository,
    )


def _finality() -> tuple[FinancialFinalityInput, ...]:
    return (
        FinancialFinalityInput(
            source="wildberries",
            source_record_id="finance-1",
            operational_date=DAY,
            financial_date=date(2026, 8, 21),
            finality=FinancialFinality.FINAL,
            evidence_code="explicit_closed_statement",
        ),
    )


def _cogs(scope) -> DirectPeriodCogsInput:
    return DirectPeriodCogsInput(
        scope=scope,
        operational_date=DAY,
        state=FinancialInputState.PROVIDED,
        amount=Decimal("-20.00"),
        source="fixture_ledger",
        source_record_id="cogs-1",
        source_endpoint="fixture_ledger",
    )


def _tax(scope) -> SourcedTaxInput:
    return SourcedTaxInput(
        scope=scope,
        operational_date=DAY,
        financial_date=date(2026, 8, 21),
        state=FinancialInputState.PROVIDED,
        amount=Decimal("-10.00"),
        source="fixture_tax",
        source_record_id="tax-1",
        source_endpoint="fixture_tax",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_resolve_operational_date_is_d_minus_one_moscow() -> None:
    explicit = resolve_operational_date(datetime(2026, 8, 20, 0, 30, tzinfo=UTC))
    assert explicit == date(2026, 8, 19)

    from zoneinfo import ZoneInfo

    aware_moscow = datetime(2026, 8, 20, 1, 30, tzinfo=ZoneInfo("Europe/Moscow"))
    assert resolve_operational_date(aware_moscow) == date(2026, 8, 19)


def test_audit_without_cogs_and_tax_stays_partial_and_never_zero_profit(tmp_path: Path) -> None:
    daily = _CountingDailyLoadersTransport()
    finance = _CountingFinanceDetailTransport()
    auditor, repository = _build_auditor(tmp_path / "partial.sqlite3", daily_transport=daily, finance_transport=finance)
    _, registration = _register(tmp_path / "partial.sqlite3", "audit_seller")

    result = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=None,
        tax=None,
    )

    assert result.ingestion_status == "ingested:daily+finance_detail"
    assert result.finance_status == FinancialStatus.PARTIAL
    assert result.audit_status == "partial"
    financial = result.analysis.pipeline.financial_flow.financial_result
    assert financial is not None
    assert financial.net_profit is None
    trace_by_component = {trace.component: trace for trace in financial.component_traces}
    assert trace_by_component[FinancialComponent.TAX].status == FinancialComponentStatus.MISSING
    assert trace_by_component[FinancialComponent.COGS].status == FinancialComponentStatus.MISSING
    assert result.raw_references.object_ids(RawObjectType.FINANCE_DETAIL)


def test_audit_success_from_persisted_raw_is_complete(tmp_path: Path) -> None:
    daily = _CountingDailyLoadersTransport()
    finance = _CountingFinanceDetailTransport()
    auditor, repository = _build_auditor(tmp_path / "complete.sqlite3", daily_transport=daily, finance_transport=finance)
    _, registration = _register(tmp_path / "complete.sqlite3", "audit_seller")

    result = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=_cogs(registration.scope),
        tax=_tax(registration.scope),
    )

    assert result.finance_status == FinancialStatus.COMPLETE
    assert result.audit_status == "complete"
    assert result.analysis.artifact.pdf_path.read_bytes().startswith(b"%PDF")
    for object_type in (
        RawObjectType.ORDERS,
        RawObjectType.SALES,
        RawObjectType.STOCKS,
        RawObjectType.SALES_FUNNEL_PRODUCTS,
        RawObjectType.ADVERTISING_PERFORMANCE,
        RawObjectType.FINANCE_DETAIL,
    ):
        assert result.raw_references.object_ids(object_type), object_type


def test_audit_rerun_does_not_refetch_when_raw_persisted(tmp_path: Path) -> None:
    daily = _CountingDailyLoadersTransport()
    finance = _CountingFinanceDetailTransport()
    auditor, repository = _build_auditor(tmp_path / "rerun.sqlite3", daily_transport=daily, finance_transport=finance)
    _, registration = _register(tmp_path / "rerun.sqlite3", "audit_seller")

    first = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=_cogs(registration.scope),
        tax=_tax(registration.scope),
    )
    second = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=_cogs(registration.scope),
        tax=_tax(registration.scope),
    )

    assert finance.calls == 1
    assert set(daily.calls.values()) == {1}
    assert len(repository.list(scope=registration.scope)) == 6
    assert first.analysis.pipeline.report_payload == second.analysis.pipeline.report_payload
    assert first.raw_references == second.raw_references


def test_audit_deterministic_replay_from_persisted_raw(tmp_path: Path) -> None:
    daily = _CountingDailyLoadersTransport()
    finance = _CountingFinanceDetailTransport()
    auditor, repository = _build_auditor(tmp_path / "replay.sqlite3", daily_transport=daily, finance_transport=finance)
    _, registration = _register(tmp_path / "replay.sqlite3", "audit_seller")

    first = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=_cogs(registration.scope),
        tax=_tax(registration.scope),
    )
    second = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=_cogs(registration.scope),
        tax=_tax(registration.scope),
    )

    assert first.raw_references == second.raw_references
    assert first.analysis.artifact.pdf_path.read_bytes() == second.analysis.artifact.pdf_path.read_bytes()
    assert first.analysis.artifact.text_path.read_text(encoding="utf-8") == second.analysis.artifact.text_path.read_text(encoding="utf-8")


def test_audit_rejects_unknown_account_and_fixture_origin_without_raw(tmp_path: Path) -> None:
    auditor, _ = _build_auditor(tmp_path / "validation.sqlite3")

    try:
        auditor.audit(account_id=UUID("00000000-0000-0000-0000-000000000999"), data_origin="test_fixture")
    except LookupError as error:
        assert "not found" in str(error)
    else:
        raise AssertionError("expected LookupError for unknown account")

    try:
        auditor.audit(account_id=UUID("00000000-0000-0000-0000-000000000999"), data_origin="unknown")
    except ValueError as error:
        assert "data_origin" in str(error)
    else:
        raise AssertionError("expected ValueError for invalid data_origin")
