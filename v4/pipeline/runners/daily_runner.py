"""Daily pipeline runner for v4 end-to-end orchestration.

Input: optional run context payload + optional output dir.
Output: unified pipeline result dictionary.
Does not implement KPI business logic or rendering logic.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import IngestionResult, RunContext, RunMode
from ...diagnostics.job_builder import build_job_diagnostics
from ...diagnostics.summary import build_job_summary
from ..contracts import PipelineRunResult
from ..modes.daily_api_mode import MODE_DESCRIPTOR as DAILY_MODE_DESCRIPTOR
from ..stages.decisions_stage import run as run_decisions_stage
from ..stages.facts_stage import run as run_facts_stage
from ..stages.input_stage import run as run_input_stage
from ..stages.metrics_stage import run as run_metrics_stage
from ..stages.normalize_stage import run as run_normalize_stage
from ..stages.outputs_stage import run as run_outputs_stage
from .seller_orchestrator import build_run_context


def _coerce_run_context(run_context: dict[str, Any] | None) -> RunContext:
    data = dict(run_context or {})
    seller_id = str(data.get("seller_id") or "").strip()
    if not seller_id:
        raise ValueError("seller_id is required for daily pipeline")

    return build_run_context(
        seller_id=seller_id,
        mode=RunMode.DAILY_API,
        run_date=data.get("run_date") or data.get("date"),
        cabinet_name=data.get("cabinet_name"),
        timezone=str(data.get("timezone") or "Europe/Moscow"),
        dry_run=bool(data.get("dry_run", False)),
    )


def _collect_warnings(
    ingestion_result: IngestionResult,
    metrics_bundle,
    facts_bundle,
    decisions_bundle,
    outputs_result: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(ingestion_result.warnings)
    warnings.extend(metrics_bundle.warnings)
    warnings.extend(facts_bundle.warnings)
    warnings.extend(decisions_bundle.warnings)

    email = outputs_result.get("email")
    if hasattr(email, "warnings"):
        warnings.extend(list(getattr(email, "warnings")))
    pdf = outputs_result.get("pdf")
    if hasattr(pdf, "warnings"):
        warnings.extend(list(getattr(pdf, "warnings")))

    seen: set[str] = set()
    deduped: list[str] = []
    for warning in warnings:
        text = str(warning)
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def run_daily_pipeline(run_context: dict | None = None, output_dir: str | None = None) -> dict:
    context = _coerce_run_context(run_context)

    ingestion_result = run_input_stage(context)
    normalized_bundle = run_normalize_stage(ingestion_result)
    metrics_bundle = run_metrics_stage(normalized_bundle)
    facts_bundle = run_facts_stage(metrics_bundle)
    decisions_bundle = run_decisions_stage(facts_bundle)
    outputs_result = run_outputs_stage(
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        mode="daily",
        output_dir=output_dir,
    )

    job_diagnostics = build_job_diagnostics(
        run_context=context,
        ingestion_result=ingestion_result,
        metrics_bundle=metrics_bundle,
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        outputs_result=outputs_result,
    )
    job_summary = build_job_summary(job_diagnostics)

    diagnostics = {
        "mode_policy": {
            "mode": DAILY_MODE_DESCRIPTOR.mode.value,
            "required_sources": list(DAILY_MODE_DESCRIPTOR.required_sources),
            "optional_sources": list(DAILY_MODE_DESCRIPTOR.optional_sources),
            "financial_contour_required": True,
        },
        "job": job_diagnostics,
        "summary": job_summary,
    }

    warnings = _collect_warnings(
        ingestion_result=ingestion_result,
        metrics_bundle=metrics_bundle,
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        outputs_result=outputs_result,
    )

    result = PipelineRunResult(
        run_context=context,
        diagnostics=diagnostics,
        metrics_bundle=metrics_bundle,
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        outputs=outputs_result,
        warnings=warnings,
    )
    return result.to_dict()

