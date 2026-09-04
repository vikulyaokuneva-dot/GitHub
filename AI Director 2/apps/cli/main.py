"""Thin CLI entry point: run one cabinet audit day via the existing ``CabinetAuditor``.

The CLI owns no pipeline logic: it parses arguments, obtains the default
application services (the same wiring as the API), delegates to
``CabinetAuditor.audit`` and prints the resulting statuses and artifact paths.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence, TextIO
from uuid import UUID

from packages.pipeline.audit import CabinetAuditResult, CabinetAuditor


def build_parser() -> argparse.ArgumentParser:
    """Parse CLI arguments; the audit date defaults to D-1 Europe/Moscow."""

    parser = argparse.ArgumentParser(
        prog="apps.cli.main",
        description="Run one WB Autopilot cabinet audit day (MVP).",
    )
    parser.add_argument("account_id", type=UUID, help="Registered account UUID (see GET /api/accounts)")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Operational date YYYY-MM-DD (default: D-1 in Europe/Moscow)",
    )
    parser.add_argument(
        "--data-origin",
        choices=("real_wb_data", "test_fixture"),
        default="real_wb_data",
        help="Data origin for the audit run (default: real_wb_data)",
    )
    return parser


def print_result(result: CabinetAuditResult, *, stream: TextIO | None = None) -> None:
    """Print the minimal MVP audit summary; no values are calculated here."""

    stream = sys.stdout if stream is None else stream
    pdf_path = Path(result.report_artifact.pdf_path)
    lines = [
        f"operational_date: {result.operational_date.isoformat()}",
        f"account_id: {result.account_id}",
        f"seller_id: {result.seller_id}",
        f"data_origin: {result.data_origin}",
        f"ingestion_status: {result.ingestion_status}",
        f"finance_status: {'no_data' if result.finance_status is None else result.finance_status.value}",
        f"audit_status: {result.audit_status}",
        f"report_pdf: {pdf_path.resolve()}",
        f"report_html: {Path(result.report_artifact.html_path).resolve()}",
        f"report_text: {Path(result.report_artifact.text_path).resolve()}",
        f"raw_references: {len(result.raw_references.objects)}",
        f"pdf_exists: {pdf_path.exists()}",
    ]
    lines.extend(f"diagnostic: {item}" for item in result.diagnostics)
    print("\n".join(lines), file=stream)


def main(argv: Sequence[str] | None = None, *, auditor: CabinetAuditor | None = None) -> int:
    """Run one audit day through the existing orchestrator; returns an exit code."""

    args = build_parser().parse_args(argv)

    if auditor is None:
        from apps.api.main import _default_audit_service

        auditor = _default_audit_service()

    try:
        result = auditor.audit(
            account_id=args.account_id,
            operational_date=args.date,
            data_origin=args.data_origin,
        )
    except LookupError as error:
        print(f"audit failed: {error}", file=sys.stderr)
        print("hint: list registered accounts via GET /api/accounts", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"audit failed: {error}", file=sys.stderr)
        return 2

    print_result(result)

    if not Path(result.report_artifact.pdf_path).exists():
        print("audit failed: report PDF was not written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
