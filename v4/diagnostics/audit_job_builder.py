"""Audit-mode diagnostics finalization helpers.

Input: pipeline bundles from audit runner.
Output: audit-focused diagnostics.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ..core.contracts import DecisionsBundle, FactsBundle, IngestionResult, MetricsBundle, RunContext
from ..pipeline.modes.audit_file_mode import get_audit_mode_flags


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
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


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

    section_statuses = {
        section_name: section.status
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

    return {
        "mode": run_context.mode.value,
        "input_path": input_path,
        "build_timestamp": None,
        "build_timestamp_note": "deterministic stage: timestamp omitted by design",
        "detected_files": dict(detected_files) if isinstance(detected_files, dict) else {},
        "missing_expected_files": list(missing_expected_files) if isinstance(missing_expected_files, list) else [],
        "file_source_flags": dict(file_source_flags) if isinstance(file_source_flags, dict) else {},
        "source_availability": source_availability,
        "missing_sources": missing_sources,
        "section_statuses": section_statuses,
        "warnings_count": len(all_warnings),
        "partial_flag": partial_flag,
        "decision_counts_by_priority": _decision_counts_by_priority(decisions_bundle),
        "output_artifact_paths": dict(artifact_paths),
        "notes": notes,
        "audit_disclaimer": get_audit_mode_flags()["disclaimer"],
    }

