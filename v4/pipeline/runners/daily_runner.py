"""Daily pipeline runner for v4 end-to-end orchestration.

Input: optional run context payload + optional output dir.
Output: unified pipeline result dictionary.
Does not implement KPI business logic or rendering logic.
"""

from __future__ import annotations

from typing import Any

from ...cabinets.registry import get_cabinet_by_seller
from ...config.features import resolve_feature_flags
from ...core.contracts import IngestionResult, RunContext, RunMode
from ...diagnostics.job_builder import build_job_diagnostics
from ...diagnostics.summary import build_job_summary
from ...warnings_utils import dedupe_warnings
from ..contracts import PipelineRunResult
from ..modes.daily_api_mode import MODE_DESCRIPTOR as DAILY_MODE_DESCRIPTOR
from ..stages.decisions_stage import run as run_decisions_stage
from ..stages.facts_stage import run as run_facts_stage
from ..stages.input_stage import run as run_input_stage
from ..stages.metrics_stage import run as run_metrics_stage
from ..stages.normalize_stage import run as run_normalize_stage
from ..stages.outputs_stage import run as run_outputs_stage
from .seller_orchestrator import build_run_context


def _coerce_run_context(run_context: dict[str, Any] | None, *, output_dir: str | None = None) -> RunContext:
    data = dict(run_context or {})
    seller_id = str(data.get("seller_id") or "").strip()
    if not seller_id:
        raise ValueError("seller_id is required for daily pipeline")

    seller_config = get_cabinet_by_seller(seller_id)
    cabinet_name = data.get("cabinet_name")
    if not cabinet_name and seller_config is not None:
        cabinet_name = seller_config.cabinet_name
    cabinet_id = data.get("cabinet_id")
    if not cabinet_id and seller_config is not None:
        cabinet_id = seller_config.cabinet_id

    run_feature_overrides = data.get("feature_flags")
    if not isinstance(run_feature_overrides, dict):
        run_feature_overrides = {}
    feature_flags = resolve_feature_flags(
        run_context={"mode": RunMode.DAILY_API.value},
        seller_config=seller_config,
        run_overrides=run_feature_overrides,
    )

    return build_run_context(
        seller_id=seller_id,
        mode=RunMode.DAILY_API,
        run_date=data.get("run_date") or data.get("date"),
        cabinet_name=cabinet_name,
        cabinet_id=cabinet_id,
        timezone=str(data.get("timezone") or "Europe/Moscow"),
        dry_run=bool(data.get("dry_run", False)),
        output_dir=output_dir or data.get("output_dir"),
        feature_flags=feature_flags,
        path_labels=data.get("path_labels") if isinstance(data.get("path_labels"), dict) else None,
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

    return dedupe_warnings(warnings)


def run_daily_pipeline(run_context: dict | None = None, output_dir: str | None = None) -> dict:
    context = _coerce_run_context(run_context, output_dir=output_dir)

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
