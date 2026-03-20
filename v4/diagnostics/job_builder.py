"""Job diagnostics finalization helpers.

Input: pipeline stage bundles and output payloads.
Output: transparent run-level diagnostics.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ..cabinets.paths import path_label
from ..core.contracts import DecisionsBundle, FactsBundle, IngestionResult, MetricsBundle, RunContext
from ..pipeline.modes.daily_api_mode import MODE_DESCRIPTOR as DAILY_MODE_DESCRIPTOR
from ..warnings_utils import dedupe_warnings


def _status_to_text(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value)


def _decision_counts_by_priority(decisions_bundle: DecisionsBundle) -> dict[str, int]:
    counts = {"P1": 0, "P2": 0, "P3": 0}
    for item in decisions_bundle.items:
        key = item.priority.value if hasattr(item.priority, "value") else str(item.priority)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _dedupe_keep_order(values: list[str]) -> list[str]:
    return dedupe_warnings(values)


def _coverage_kind(*, status_text: str, reason: str) -> str:
    if reason in {"auth_error", "request_failed", "parse_failed", "normalized_empty"}:
        return "source_failed"
    if reason == "no_data_for_date":
        return "source_unavailable_for_selected_date"
    if status_text == "missing" and reason == "empty_payload":
        return "source_empty_but_valid"
    if status_text in {"missing", "not_implemented"}:
        return "source_missing"
    if status_text == "error":
        return "source_failed"
    if status_text == "partial":
        return "source_partial"
    return "source_available"


def build_job_diagnostics(
    *,
    run_context: RunContext,
    ingestion_result: IngestionResult,
    metrics_bundle: MetricsBundle,
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    outputs_result: dict[str, Any],
) -> dict[str, Any]:
    source_availability = {
        source_name: _status_to_text(status)
        for source_name, status in ingestion_result.source_flags.items()
    }
    raw_reason_map = ingestion_result.raw_bundle.diagnostics.get("source_reason_map")
    metrics_diag = metrics_bundle.diagnostics if isinstance(getattr(metrics_bundle, "diagnostics", None), dict) else {}
    metric_reason_map = metrics_diag.get("source_reason_map") if isinstance(metrics_diag, dict) else None
    source_reason_map = (
        {str(k): str(v) for k, v in raw_reason_map.items()}
        if isinstance(raw_reason_map, dict)
        else {}
    )
    if isinstance(metric_reason_map, dict):
        source_reason_map.update({str(k): str(v) for k, v in metric_reason_map.items()})
    for source_name, status_text in source_availability.items():
        if source_name in source_reason_map:
            continue
        status_token = str(status_text).strip().lower()
        if status_token == "ok":
            source_reason_map[source_name] = "ok"
        elif status_token == "partial":
            source_reason_map[source_name] = "partial_source"
        elif status_token == "error":
            source_reason_map[source_name] = "request_failed"
        elif status_token == "missing":
            source_reason_map[source_name] = "empty_payload"
        else:
            source_reason_map[source_name] = "source_missing"

    missing_sources = [
        source_name
        for source_name, status in source_availability.items()
        if status not in {"ok", "partial"}
    ]
    partial_sources = [
        source_name
        for source_name, status in source_availability.items()
        if status == "partial" or str(source_reason_map.get(source_name, "")).strip().lower() in {"parse_failed", "normalized_empty"}
    ]
    source_coverage_summary = {
        source_name: _coverage_kind(
            status_text=str(source_availability.get(source_name, "")).strip().lower(),
            reason=str(source_reason_map.get(source_name, "")).strip().lower(),
        )
        for source_name in source_availability.keys()
    }
    required_missing_sources = [
        source_name
        for source_name in DAILY_MODE_DESCRIPTOR.required_sources
        if source_availability.get(source_name) not in {"ok", "partial"}
    ]
    optional_missing_sources = [
        source_name
        for source_name in DAILY_MODE_DESCRIPTOR.optional_sources
        if source_availability.get(source_name) not in {"ok", "partial"}
    ]

    section_statuses = {
        section_name: _status_to_text(section.status)
        for section_name, section in facts_bundle.sections.items()
    }

    all_warnings = []
    all_warnings.extend(ingestion_result.warnings)
    all_warnings.extend(metrics_bundle.warnings)
    all_warnings.extend(facts_bundle.warnings)
    all_warnings.extend(decisions_bundle.warnings)
    artifacts = outputs_result.get("artifacts", {}) if isinstance(outputs_result, dict) else {}
    artifact_paths = artifacts.get("saved_files", {}) if isinstance(artifacts, dict) else {}
    artifact_labels = {
        str(name): str(path_label(path) or "")
        for name, path in (artifact_paths.items() if isinstance(artifact_paths, dict) else [])
    }
    all_warnings = _dedupe_keep_order([str(w) for w in all_warnings])

    partial_flag = bool(
        required_missing_sources
        or partial_sources
        or facts_bundle.data_quality.get("partial_sections")
        or facts_bundle.data_quality.get("unavailable_sections")
        or any(status == "partial" for status in section_statuses.values())
    )

    notes: list[str] = []
    if required_missing_sources:
        notes.append(f"Required sources missing: {required_missing_sources}")
    if optional_missing_sources:
        notes.append(f"Optional sources missing: {optional_missing_sources}")
    if partial_sources:
        notes.append(f"Partial sources: {partial_sources}")
    if partial_flag:
        notes.append("Run completed with partial data; outputs are conservative.")
    if not notes:
        notes.append("Run completed with available required sources.")

    return {
        "mode": run_context.mode.value,
        "seller_id": run_context.seller_id,
        "cabinet_id": run_context.cabinet_id,
        "cabinet_name": run_context.cabinet_name,
        "requested_date": run_context.requested_date_iso,
        "resolved_date": run_context.resolved_date_iso,
        "dry_run": bool(run_context.dry_run),
        "feature_flags": dict(run_context.feature_flags),
        "path_labels": dict(run_context.path_labels),
        "output_dir_label": run_context.output_dir,
        "build_timestamp": None,
        "build_timestamp_note": "deterministic stage: timestamp omitted by design",
        "source_availability": source_availability,
        "source_reason_map": source_reason_map,
        "source_coverage_summary": source_coverage_summary,
        "missing_sources": missing_sources,
        "partial_sources": partial_sources,
        "required_missing_sources": required_missing_sources,
        "optional_missing_sources": optional_missing_sources,
        "section_statuses": section_statuses,
        "warnings_count": len(all_warnings),
        "warnings": list(all_warnings),
        "partial_flag": partial_flag,
        "decision_counts_by_priority": _decision_counts_by_priority(decisions_bundle),
        "output_artifact_paths": artifact_labels,
        "notes": notes,
    }
