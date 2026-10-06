"""Regression: the audit must reuse the durable finance raw of the EXACT date.

Guards the raw-first finance policy under a long WB rate limit:

    audit(date)
      -> durable authoritative finance raw for exactly ``date``?
           YES -> reuse it (0 WB finance requests), normalize, Finance Kernel
           NO  -> one ordinary live WB request
                    200 -> persist raw and use it
                    429 -> finance unavailable, never a fabricated P&L

A raw that exists but cannot be validated is never used silently: the audit
falls back to the live/error path and reports the exclusion.

Every test counts HTTP calls through the transport boundary, so "no WB
request" is an observation, not an assumption.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from packages.accounts import (
    AccountRegistrationService,
    CredentialRef,
    SQLiteAccountRegistrationRepository,
)
from packages.finance.contracts import FinancialStatus
from packages.pipeline import CabinetAuditor, DailyAnalysisService
from packages.wb_core.contracts import (
    FINANCE_DETAIL_ENDPOINT,
    RawObject,
    RawObjectType,
    TenantAccountScope,
)
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository

DAY = date(2026, 9, 10)
NEXT_DAY = date(2026, 9, 11)

RATE_LIMIT_REASON = (
    "finance_detail WB request failed with status 429 "
    "(POST https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed): "
    "retry_window_exhausted (origin=ag-finance, requestId=bbe5b8ce, "
    "rate_limit_headers: x_ratelimit_retry=11505, x_ratelimit_remaining=0)"
)


def _finance_row(*, rrd_id: str, operational_date: date) -> list[dict[str, object]]:
    return [
        {
            "rrdId": rrd_id,
            "rrDate": date.fromordinal(operational_date.toordinal() + 1).isoformat(),
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


class _CountingFinanceTransport:
    """Live finance transport: counts every WB call and can be rate-limited."""

    def __init__(self, *, rate_limited: bool = False) -> None:
        self.calls = 0
        self._rate_limited = rate_limited

    def fetch_finance_detail(self, *, operational_date: date) -> tuple[list[dict[str, object]], bytes]:
        self.calls += 1
        if self._rate_limited:
            raise RuntimeError(RATE_LIMIT_REASON)
        payload = _finance_row(rrd_id=f"finance-{operational_date.isoformat()}", operational_date=operational_date)
        return payload, json.dumps(payload, separators=(",", ":")).encode("utf-8")


class _WorkingLoaders:
    """Every daily loader succeeds, so the day always has operational sources."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

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
        return {
            "payload": [
                {
                    "srid": "sale-1",
                    "nmId": 1001,
                    "quantity": "1",
                    "priceWithDisc": "50.00",
                    "date": operational_date.isoformat(),
                }
            ]
        }

    def load_stocks(self, *, operational_date: date) -> dict[str, object]:
        self._count("stocks")
        return {"payload": {"data": [{"nmId": 1001, "quantity": "10", "inWayToClient": "1", "inWayFromClient": "2"}]}}

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, object]:
        self._count("funnel")
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
                                    "orderCount": 1,
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
        self._count("ads")
        return {"payload": {"data": [{"advertId": 1, "nmId": 1001, "sum": "10.00"}]}}


def _register(database_path: Path) -> Any:
    accounts = SQLiteAccountRegistrationRepository(database_path)
    registration = AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id="finance_reuse_seller",
        credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL"),
    )
    return accounts, registration


def _build(
    database_path: Path,
    registration: Any,
    *,
    finance_transport: _CountingFinanceTransport,
) -> tuple[CabinetAuditor, SQLiteRawObjectRepository]:
    """Production-shaped wiring with fresh counters; sharing nothing mutable."""

    accounts = SQLiteAccountRegistrationRepository(database_path)
    repository = SQLiteRawObjectRepository(database_path)
    daily = WBDailyIngestionService(repository=repository, loaders=_WorkingLoaders())
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
    return auditor, repository


def _audit(auditor: CabinetAuditor, registration: Any, *, day: date = DAY) -> Any:
    return auditor.audit(
        account_id=registration.account_id,
        operational_date=day,
        data_origin="real_wb_data",
    )


def _seed_durable_raws(database_path: Path) -> tuple[Any, SQLiteRawObjectRepository]:
    """First ordinary audit: every source, finance included, becomes durable."""

    _, registration = _register(database_path)
    seed_finance = _CountingFinanceTransport()
    auditor, repository = _build(database_path, registration, finance_transport=seed_finance)
    _audit(auditor, registration)
    assert seed_finance.calls == 1, "the seeding audit must fetch finance exactly once"
    assert repository.list(scope=registration.scope, endpoint_name=FINANCE_DETAIL_ENDPOINT.name)
    return registration, repository


def _save_corrupt_finance_raw(
    repository: SQLiteRawObjectRepository,
    *,
    scope: TenantAccountScope,
    operational_date: date,
) -> str:
    """Persist a loadable but unusable finance raw (a real corruption case)."""

    payload = {"data": "corrupted"}
    raw_payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    raw_object = RawObject(
        object_id=hashlib.sha256(b"corrupt-durable-finance-raw").hexdigest(),
        scope=scope,
        endpoint=FINANCE_DETAIL_ENDPOINT,
        object_type=FINANCE_DETAIL_ENDPOINT.object_type,
        source=FINANCE_DETAIL_ENDPOINT.source,
        retrieved_at=datetime(2026, 9, 11, 3, 0, tzinfo=UTC),
        operational_date=operational_date,
        request_scope={
            "dateFrom": operational_date.isoformat(),
            "dateTo": operational_date.isoformat(),
            "period": "daily",
            "limit": 100000,
            "rrdId": 0,
        },
        payload=payload,
        raw_payload_bytes=raw_payload_bytes,
        schema_version=FINANCE_DETAIL_ENDPOINT.schema_version,
    )
    repository.save(raw_object)
    return raw_object.object_id


# ---------------------------------------------------------------------------
# Scenario A: durable raw for the requested date -> 0 WB finance requests.
# ---------------------------------------------------------------------------


def test_scenario_a_durable_raw_is_reused_without_any_wb_finance_request(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario-a.sqlite3"
    registration, _ = _seed_durable_raws(database_path)

    probe = _CountingFinanceTransport()
    auditor, _ = _build(database_path, registration, finance_transport=probe)

    result = _audit(auditor, registration)

    # THE contract: an existing authoritative raw means no WB finance traffic.
    assert probe.calls == 0

    # raw -> normalize -> Finance Kernel.
    finance_records = result.analysis.pipeline.finance_records
    assert finance_records, "the durable raw must reach the analysis as finance records"
    assert all(record.operational_date == DAY for record in finance_records)
    financial = result.analysis.pipeline.financial_flow.financial_result
    assert financial is not None
    assert financial.status == FinancialStatus.PARTIAL  # no finality/cogs/tax declared
    assert result.finance_status == FinancialStatus.PARTIAL
    assert result.audit_status == "partial"
    assert result.raw_references.object_ids(RawObjectType.FINANCE_DETAIL)

    # The reuse is visible in the audit result instead of being silent.
    joined = "\n".join(result.diagnostics)
    assert "durable raw" in joined, result.diagnostics
    assert "source_unavailable:finance_detail" not in joined


# ---------------------------------------------------------------------------
# Scenario B: a raw of another date must not satisfy this audit.
# ---------------------------------------------------------------------------


def test_scenario_b_raw_of_another_date_is_never_used(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario-b.sqlite3"
    registration, _ = _seed_durable_raws(database_path)

    probe = _CountingFinanceTransport()
    auditor, repository = _build(database_path, registration, finance_transport=probe)

    result = _audit(auditor, registration, day=NEXT_DAY)

    # Exact-date mismatch -> the ordinary live path runs exactly once.
    assert probe.calls == 1

    finance_records = result.analysis.pipeline.finance_records
    assert finance_records
    # The persisted DAY raw must not leak into NEXT_DAY's audit.
    assert all(record.operational_date == NEXT_DAY for record in finance_records)
    assert [record.source_record_id for record in finance_records] == [f"finance-{NEXT_DAY.isoformat()}"]
    stored_dates = sorted(
        str(raw.operational_date)
        for raw in repository.list(scope=registration.scope, endpoint_name=FINANCE_DETAIL_ENDPOINT.name)
    )
    assert stored_dates == [DAY.isoformat(), NEXT_DAY.isoformat()]
    # Reuse is NOT claimed when the data came from a fresh request.
    assert "durable raw" not in "\n".join(result.diagnostics)


# ---------------------------------------------------------------------------
# Scenario C: no durable raw + WB 429 -> honest unavailability, no zeros.
# ---------------------------------------------------------------------------


def test_scenario_c_rate_limited_live_path_yields_unavailable_and_never_zeroes(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario-c.sqlite3"
    _, registration = _register(database_path)

    probe = _CountingFinanceTransport(rate_limited=True)
    auditor, repository = _build(database_path, registration, finance_transport=probe)

    result = _audit(auditor, registration)

    # The live path was attempted, bounded by the existing retry policy.
    assert probe.calls == 1
    assert result.ingestion_status == "ingested:daily+degraded"
    joined = "\n".join(result.diagnostics)
    assert "source_unavailable:finance_detail" in joined
    assert "retry_window_exhausted" in joined

    # No authoritative P&L and nothing fabricated as zero.
    assert result.finance_status is None
    assert result.audit_status == "no_data"
    assert result.analysis.pipeline.finance_records == ()
    assert result.analysis.pipeline.financial_flow.financial_result is None
    assert result.analysis.pipeline.report_payload.financial is None
    assert "no authoritative P&L" in joined
    assert not repository.list(scope=registration.scope, endpoint_name=FINANCE_DETAIL_ENDPOINT.name)


# ---------------------------------------------------------------------------
# Scenario D: a durable raw that fails validation must not be used silently.
# ---------------------------------------------------------------------------


def test_scenario_d_corrupt_durable_raw_falls_back_to_the_live_path(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario-d-live.sqlite3"
    _, registration = _register(database_path)
    repository = SQLiteRawObjectRepository(database_path)
    _save_corrupt_finance_raw(repository, scope=registration.scope, operational_date=DAY)

    probe = _CountingFinanceTransport()
    auditor, _ = _build(database_path, registration, finance_transport=probe)

    result = _audit(auditor, registration)

    # The unusable raw triggered exactly one live request instead of a silent reuse.
    assert probe.calls == 1
    finance_records = result.analysis.pipeline.finance_records
    assert finance_records
    assert [record.source_record_id for record in finance_records] == [f"finance-{DAY.isoformat()}"]
    assert result.finance_status is not None
    joined = "\n".join(result.diagnostics)
    assert "excluded" in joined and "not usable" in joined, result.diagnostics
    # The corrupt payload never becomes finance evidence.
    assert all(record.source_record_id != "corrupted" for record in finance_records)


def test_scenario_d_corrupt_durable_raw_with_rate_limited_live_path_is_unavailable(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario-d-outage.sqlite3"
    _, registration = _register(database_path)
    repository = SQLiteRawObjectRepository(database_path)
    _save_corrupt_finance_raw(repository, scope=registration.scope, operational_date=DAY)

    probe = _CountingFinanceTransport(rate_limited=True)
    auditor, _ = _build(database_path, registration, finance_transport=probe)

    result = _audit(auditor, registration)

    assert probe.calls == 1
    assert "source_unavailable:finance_detail" in "\n".join(result.diagnostics)
    assert result.finance_status is None
    assert result.audit_status == "no_data"
    assert result.analysis.pipeline.financial_flow.financial_result is None
    assert result.analysis.pipeline.report_payload.financial is None


# ---------------------------------------------------------------------------
# Scenario E: repeated audits of the same date never touch the WB endpoint.
# ---------------------------------------------------------------------------


def test_scenario_e_repeated_audits_keep_using_the_durable_raw(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario-e.sqlite3"
    registration, _ = _seed_durable_raws(database_path)

    first_probe = _CountingFinanceTransport()
    first_auditor, _ = _build(database_path, registration, finance_transport=first_probe)
    first = _audit(first_auditor, registration)

    second_probe = _CountingFinanceTransport()
    second_auditor, _ = _build(database_path, registration, finance_transport=second_probe)
    second = _audit(second_auditor, registration)

    assert first_probe.calls == 0
    assert second_probe.calls == 0
    assert first.finance_status is not None
    assert second.finance_status == first.finance_status
    assert first.raw_references == second.raw_references
    assert first.analysis.pipeline.report_payload == second.analysis.pipeline.report_payload
    reuse_notes = [line for line in second.diagnostics if "durable raw" in line]
    assert len(reuse_notes) == 1, second.diagnostics
