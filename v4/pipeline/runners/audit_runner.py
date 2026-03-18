"""Audit pipeline runner for v4 end-to-end orchestration.

Input: input path + optional run context + optional output dir.
Output: unified pipeline result dictionary.
Does not implement KPI business logic.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import RunContext, RunMode
from ...diagnostics.audit_job_builder import build_audit_job_diagnostics
from ...diagnostics.audit_summary import build_audit_summary
from ...ingestion.files.bundle import build_file_raw_bundle
from ..contracts import PipelineRunResult
from ..modes.audit_file_mode import MODE_DESCRIPTOR as AUDIT_MODE_DESCRIPTOR, get_audit_mode_flags
from ..stages.decisions_stage import run as run_decisions_stage
from ..stages.facts_stage import run as run_facts_stage
from ..stages.metrics_stage import run as run_metrics_stage
from ..stages.normalize_stage import run as run_normalize_stage
from ..stages.outputs_stage import run as run_outputs_stage
from .seller_orchestrator import build_run_context


def _coerce_run_context(run_context: dict[str, Any] | None) -> RunContext:
    data = dict(run_context or {})
    seller_id = str(data.get("seller_id") or "seller_001").strip()
    if not seller_id:
        seller_id = "seller_001"

    return build_run_context(
        seller_id=seller_id,
        mode=RunMode.AUDIT_FILE,
        run_date=data.get("run_date") or data.get("date"),
        cabinet_name=data.get("cabinet_name"),
        timezone=str(data.get("timezone") or "Europe/Moscow"),
        dry_run=bool(data.get("dry_run", False)),
    )


def _collect_warnings(
    ingestion_result,
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
    out: list[str] = []
    for warning in warnings:
        text = str(warning)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def run_audit_pipeline(
    input_path: str,
    run_context: dict | None = None,
    output_dir: str | None = None,
) -> dict:
    if not str(input_path).strip():
        raise ValueError("input_path is required for audit pipeline")

    context = _coerce_run_context(run_context)
    ingestion_result = build_file_raw_bundle(input_path=input_path, run_context=context)
    normalized_bundle = run_normalize_stage(ingestion_result)
    metrics_bundle = run_metrics_stage(normalized_bundle)
    facts_bundle = run_facts_stage(metrics_bundle)
    decisions_bundle = run_decisions_stage(facts_bundle)
    outputs_result = run_outputs_stage(
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        mode="audit",
        output_dir=output_dir,
    )

    job_diagnostics = build_audit_job_diagnostics(
        run_context=context,
        input_path=input_path,
        ingestion_result=ingestion_result,
        metrics_bundle=metrics_bundle,
        facts_bundle=facts_bundle,
        decisions_bundle=decisions_bundle,
        outputs_result=outputs_result,
    )
    audit_summary = build_audit_summary(job_diagnostics)
    diagnostics = {
        "mode_policy": {
            "mode": AUDIT_MODE_DESCRIPTOR.mode.value,
            "required_file_inputs": list(AUDIT_MODE_DESCRIPTOR.required_file_inputs),
            "optional_file_inputs": list(AUDIT_MODE_DESCRIPTOR.optional_file_inputs),
            "required_raw_sources": list(AUDIT_MODE_DESCRIPTOR.required_raw_sources),
            "optional_raw_sources": list(AUDIT_MODE_DESCRIPTOR.optional_raw_sources),
            "audit_flags": get_audit_mode_flags(),
        },
        "job": job_diagnostics,
        "summary": audit_summary,
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

