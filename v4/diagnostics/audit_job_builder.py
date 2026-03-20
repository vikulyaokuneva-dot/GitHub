"""Audit-mode diagnostics finalization helpers.

Input: pipeline bundles from audit runner.
Output: audit-focused diagnostics.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ..cabinets.paths import path_label
from ..core.contracts import DecisionsBundle, FactsBundle, IngestionResult, MetricsBundle, RunContext
from ..pipeline.modes.audit_file_mode import get_audit_mode_flags
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


def _dedupe(values: list[str]) -> list[str]:
    return dedupe_warnings(values)


def _coverage_kind(*, status_text: str, reason: str) -> str:
    if reason in {"auth_error", "auth_failed", "request_failed", "parse_failed", "normalized_empty"}:
        return "source_failed"
    if reason in {"no_data_for_date", "no_realization_in_window"}:
        return "source_unavailable_for_selected_date"
    if status_text == "missing" and reason in {"empty_payload", "ok_empty_payload"}:
        return "source_empty_but_valid"
    if status_text in {"missing", "not_implemented"}:
        return "source_missing"
    if status_text == "error":
        return "source_failed"
    if status_text == "partial":
        return "source_partial"
    return "source_available"


def build_audit_job_diagnostics(
    *,
    run_context: RunContext,
    input_path: str,
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
    missing_sources = [
        source_name
        for source_name, status in source_availability.items()
        if status not in {"ok", "partial"}
    ]
    source_reason_map = {
        source_name: (
            "ok"
            if status == "ok"
            else "partial_source"
            if status == "partial"
            else "empty_payload"
            if status == "missing"
            else "request_failed"
            if status == "error"
            else "source_missing"
        )
        for source_name, status in source_availability.items()
    }
    partial_sources = [
        source_name
        for source_name, status in source_availability.items()
        if status == "partial"
    ]
    source_coverage_summary = {
        source_name: _coverage_kind(
            status_text=str(status).strip().lower(),
            reason=str(source_reason_map.get(source_name, "")).strip().lower(),
        )
        for source_name, status in source_availability.items()
    }

    section_statuses = {
        section_name: _status_to_text(section.status)
        for section_name, section in facts_bundle.sections.items()
    }

    all_warnings: list[str] = []
    all_warnings.extend(ingestion_result.warnings)
    all_warnings.extend(metrics_bundle.warnings)
    all_warnings.extend(facts_bundle.warnings)
    all_warnings.extend(decisions_bundle.warnings)
    all_warnings = _dedupe(all_warnings)

    artifacts = outputs_result.get("artifacts", {}) if isinstance(outputs_result, dict) else {}
    artifact_paths = artifacts.get("saved_files", {}) if isinstance(artifacts, dict) else {}
    artifact_labels = {
        str(name): str(path_label(path) or "")
        for name, path in (artifact_paths.items() if isinstance(artifact_paths, dict) else [])
    }

    ingestion_diag = ingestion_result.raw_bundle.diagnostics
    detected_files = ingestion_diag.get("detected_files", {})
    missing_expected_files = ingestion_diag.get("missing_expected_files", [])
    file_source_flags = ingestion_diag.get("file_source_flags", {})

    partial_flag = bool(
        missing_sources
        or missing_expected_files
        or facts_bundle.data_quality.get("partial_sections")
        or facts_bundle.data_quality.get("unavailable_sections")
        or any(status == "partial" for status in section_statuses.values())
    )

    notes = [
        get_audit_mode_flags()["disclaimer"],
        "Audit mode is file-only and does not use API ingestion.",
    ]
    if missing_expected_files:
        notes.append(f"Missing expected files: {list(missing_expected_files)}")

    input_label = run_context.input_path_label or path_label(input_path)

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
        "input_path": str(input_label or ""),
        "input_path_label": input_label,
        "build_timestamp": None,
        "build_timestamp_note": "deterministic stage: timestamp omitted by design",
        "detected_files": dict(detected_files) if isinstance(detected_files, dict) else {},
        "missing_expected_files": list(missing_expected_files) if isinstance(missing_expected_files, list) else [],
        "file_source_flags": dict(file_source_flags) if isinstance(file_source_flags, dict) else {},
        "source_availability": source_availability,
        "source_reason_map": source_reason_map,
        "source_coverage_summary": source_coverage_summary,
        "missing_sources": missing_sources,
        "partial_sources": partial_sources,
        "section_statuses": section_statuses,
        "warnings_count": len(all_warnings),
        "warnings": list(all_warnings),
        "partial_flag": partial_flag,
        "decision_counts_by_priority": _decision_counts_by_priority(decisions_bundle),
        "output_artifact_paths": artifact_labels,
        "notes": notes,
        "audit_disclaimer": get_audit_mode_flags()["disclaimer"],
    }
