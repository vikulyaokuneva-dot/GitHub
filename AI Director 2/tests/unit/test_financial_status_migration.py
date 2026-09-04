from __future__ import annotations

from datetime import date

from packages.finance.contracts import FinancialFinality, FinancialFinalityInput, FinancialStatus
from packages.finance.status import assess_financial_finality


def _evidence(finality: FinancialFinality, *, record_id: str = "rrd-1") -> FinancialFinalityInput:
    return FinancialFinalityInput(
        source="wildberries",
        source_record_id=record_id,
        source_endpoint="finance_detail",
        operational_date=date(2026, 8, 20),
        financial_date=date(2026, 8, 21),
        finality=finality,
        evidence_code="explicit_test_evidence",
    )


def test_financial_rows_without_evidence_remain_partial() -> None:
    assessment = assess_financial_finality((), has_financial_facts=True)

    assert assessment.finality == FinancialFinality.UNKNOWN
    assert assessment.status == FinancialStatus.PARTIAL
    assert "no explicit finality" in assessment.diagnostics[0]


def test_explicit_finality_can_be_complete_only_without_lag() -> None:
    complete = assess_financial_finality((_evidence(FinancialFinality.FINAL),), has_financial_facts=True)
    lagged = assess_financial_finality(
        (_evidence(FinancialFinality.FINAL),), has_financial_facts=True, financial_lag=True
    )

    assert complete.status == FinancialStatus.COMPLETE
    assert lagged.status == FinancialStatus.PARTIAL
    assert lagged.finality == FinancialFinality.FINAL


def test_provisional_conflicting_and_missing_finance_have_distinct_statuses() -> None:
    provisional = assess_financial_finality((_evidence(FinancialFinality.PROVISIONAL),), has_financial_facts=True)
    conflict = assess_financial_finality(
        (_evidence(FinancialFinality.FINAL), _evidence(FinancialFinality.PROVISIONAL, record_id="rrd-2")),
        has_financial_facts=True,
    )
    missing = assess_financial_finality((), has_financial_facts=False)

    assert provisional.status == FinancialStatus.PARTIAL
    assert conflict.status == FinancialStatus.CONFLICT
    assert missing.status == FinancialStatus.INSUFFICIENT_DATA
