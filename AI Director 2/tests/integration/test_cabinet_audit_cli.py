"""Integration test: the CLI runs one audit day end-to-end via CabinetAuditor."""

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from apps.cli.main import build_parser, main, print_result
from packages.accounts import AccountRegistrationService, CredentialRef
from packages.finance.contracts import (
    FinancialFinality,
    FinancialFinalityInput,
    FinancialInputState,
)
from packages.pipeline import CabinetAuditor, DailyAnalysisService
from packages.products.contracts import DirectPeriodCogsInput
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import RawObjectType
from packages.wb_core.daily_ingestion import WBDailyIngestionService
from packages.wb_core.finance_ingestion import WBFinanceDetailIngestionService
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository
from tests.integration.test_cabinet_audit import (
    DAY,
    _CountingDailyLoadersTransport,
    _CountingFinanceDetailTransport,
    _cogs,
    _finality,
    _register,
    _tax,
)


def _build(tmp_path: Path) -> tuple[CabinetAuditor, object]:
    accounts, registration = _register(tmp_path / "cli.sqlite3", "cli_seller")
    repository = SQLiteRawObjectRepository(tmp_path / "cli.sqlite3")
    daily = _CountingDailyLoadersTransport()
    finance = _CountingFinanceDetailTransport()
    daily_ingestion = WBDailyIngestionService(repository=repository, loaders=daily)
    finance_ingestion = WBFinanceDetailIngestionService(repository=repository, transport=finance)
    analysis = DailyAnalysisService(
        accounts=accounts,
        raw_repository=repository,
        reports_root=tmp_path / "reports",
        daily_ingestion=daily_ingestion,
        finance_detail_ingestion=finance_ingestion,
    )
    auditor = CabinetAuditor(
        accounts=accounts,
        raw_repository=repository,
        analysis_service=analysis,
        daily_ingestion=daily_ingestion,
        finance_detail_ingestion=finance_ingestion,
    )
    return auditor, registration


def test_cli_runs_one_audit_day_and_prints_artifacts(tmp_path: Path, capsys) -> None:
    auditor, registration = _build(tmp_path)
    exit_code = main(
        [
            str(registration.account_id),
            "--date",
            DAY.isoformat(),
            "--data-origin",
            "real_wb_data",
        ],
        auditor=auditor,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"operational_date: {DAY.isoformat()}" in output
    assert f"account_id: {registration.account_id}" in output
    assert "ingestion_status: ingested:daily+finance_detail" in output
    # The CLI takes no COGS/tax inputs, so a default run must stay honest PARTIAL.
    assert "finance_status: partial" in output
    assert "audit_status: partial" in output
    assert "raw_references: 6" in output
    assert "pdf_exists: True" in output

    pdf_line = next(line for line in output.splitlines() if line.startswith("report_pdf: "))
    pdf_path = Path(pdf_line.removeprefix("report_pdf: "))
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert "reports" in str(pdf_path)


def test_cli_print_result_exposes_diagnostics(tmp_path: Path, capsys) -> None:
    auditor, registration = _build(tmp_path)
    result = auditor.audit(
        account_id=registration.account_id,
        operational_date=DAY,
        data_origin="real_wb_data",
        finality=_finality(),
        period_cogs=_cogs(registration.scope),
        tax=_tax(registration.scope),
    )
    stream = io.StringIO()
    print_result(result, stream=stream)
    text = stream.getvalue()
    assert f"operational_date: {DAY.isoformat()}" in text
    assert "audit_status: complete" in text


def test_cli_rejects_unknown_account_with_exit_code_2(tmp_path: Path, capsys) -> None:
    from uuid import UUID

    auditor, _ = _build(tmp_path)
    exit_code = main(
        [str(UUID("00000000-0000-0000-0000-000000000999")), "--date", DAY.isoformat()],
        auditor=auditor,
    )
    assert exit_code == 2
    assert "audit failed" in capsys.readouterr().err


def test_cli_defaults_date_to_d_minus_one_moscow() -> None:
    from zoneinfo import ZoneInfo

    from packages.pipeline.audit import resolve_operational_date

    args = build_parser().parse_args(["00000000-0000-0000-0000-000000000001"])
    assert args.date is None
    assert args.data_origin == "real_wb_data"
    assert resolve_operational_date(datetime(2026, 8, 20, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))) == date(2026, 8, 19)
