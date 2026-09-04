"""Evidence-based financial lifecycle assessment without inferred finality."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .contracts import FinancialFinality, FinancialFinalityInput, FinancialStatus


class FinancialFinalityAssessment(BaseModel):
    """Finality evidence and its safe lifecycle interpretation."""

    model_config = ConfigDict(frozen=True)

    finality: FinancialFinality
    status: FinancialStatus
    evidence: tuple[FinancialFinalityInput, ...]
    diagnostics: tuple[str, ...] = ()


def assess_financial_finality(
    evidence: tuple[FinancialFinalityInput, ...],
    *,
    has_financial_facts: bool,
    financial_lag: bool = False,
    has_conflict: bool = False,
    insufficient_data: bool = False,
) -> FinancialFinalityAssessment:
    """Interpret only supplied evidence; row presence never creates finality."""

    ordered = tuple(sorted(evidence, key=lambda item: (item.source_record_id, item.evidence_code)))
    if has_conflict:
        return FinancialFinalityAssessment(
            finality=FinancialFinality.UNKNOWN,
            status=FinancialStatus.CONFLICT,
            evidence=ordered,
            diagnostics=("financial status conflict; no finality conclusion",),
        )
    if insufficient_data or not has_financial_facts:
        return FinancialFinalityAssessment(
            finality=FinancialFinality.UNKNOWN,
            status=FinancialStatus.INSUFFICIENT_DATA,
            evidence=ordered,
            diagnostics=("financial facts are absent or insufficient",),
        )
    if not ordered:
        return FinancialFinalityAssessment(
            finality=FinancialFinality.UNKNOWN,
            status=FinancialStatus.PARTIAL,
            evidence=(),
            diagnostics=("financial rows have no explicit finality evidence",),
        )
    values = {item.finality for item in ordered}
    if len(values) > 1:
        return FinancialFinalityAssessment(
            finality=FinancialFinality.UNKNOWN,
            status=FinancialStatus.CONFLICT,
            evidence=ordered,
            diagnostics=("financial finality evidence conflicts",),
        )
    finality = next(iter(values))
    if finality == FinancialFinality.FINAL and not financial_lag:
        return FinancialFinalityAssessment(finality=finality, status=FinancialStatus.COMPLETE, evidence=ordered)
    diagnostics = ("financial source is lagged",) if financial_lag else ("financial finality is not explicit final",)
    return FinancialFinalityAssessment(
        finality=finality,
        status=FinancialStatus.PARTIAL,
        evidence=ordered,
        diagnostics=diagnostics,
    )
