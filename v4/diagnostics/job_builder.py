"""Job diagnostics finalization helpers.

Input: pipeline stage bundles and output payloads.
Output: transparent run-level diagnostics.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ..core.contracts import DecisionsBundle, FactsBundle, IngestionResult, MetricsBundle, RunContext
from ..pipeline.modes.daily_api_mode import MODE_DESCRIPTOR as DAILY_MODE_DESCRIPTOR


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
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


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
    missing_sources = [
        source_name
        for source_name, status in source_availability.items()
        if status not in {"ok", "partial"}
    ]
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
    all_warnings = _dedupe_keep_order([str(w) for w in all_warnings])

    partial_flag = bool(
        required_missing_sources
        or facts_bundle.data_quality.get("partial_sections")
        or facts_bundle.data_quality.get("unavailable_sections")
        or any(status == "partial" for status in section_statuses.values())
    )

    notes: list[str] = []
    if required_missing_sources:
        notes.append(f"Required sources missing: {required_missing_sources}")
    if optional_missing_sources:
        notes.append(f"Optional sources missing: {optional_missing_sources}")
    if partial_flag:
        notes.append("Run completed with partial data; outputs are conservative.")
    if not notes:
        notes.append("Run completed with available required sources.")

    return {
        "mode": run_context.mode.value,
        "build_timestamp": None,
        "build_timestamp_note": "deterministic stage: timestamp omitted by design",
        "source_availability": source_availability,
        "missing_sources": missing_sources,
        "required_missing_sources": required_missing_sources,
        "optional_missing_sources": optional_missing_sources,
        "section_statuses": section_statuses,
        "warnings_count": len(all_warnings),
        "partial_flag": partial_flag,
        "decision_counts_by_priority": _decision_counts_by_priority(decisions_bundle),
        "output_artifact_paths": dict(artifact_paths),
        "notes": notes,
    }
