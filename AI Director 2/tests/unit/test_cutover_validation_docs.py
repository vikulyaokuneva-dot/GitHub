from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_cutover_reports_record_blocked_real_data_replay_without_claiming_parity() -> None:
    report = (PROJECT_ROOT / "reports" / "METRIC_PARITY_REPORT.md").read_text(encoding="utf-8")
    coverage = (PROJECT_ROOT / "docs" / "architecture" / "LEGACY_COVERAGE.md").read_text(encoding="utf-8")

    assert "**Cutover validation is blocked.**" in report
    assert "No cent-level `Decimal` comparison was executed." in report
    assert "**Decision: NO-GO.**" in report
    assert "Stage 9 remains blocked" in report
    assert "zero executable imports" in coverage
    assert "production cutover" in coverage
