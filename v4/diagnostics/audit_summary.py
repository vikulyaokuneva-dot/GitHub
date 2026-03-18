"""Audit-mode summary builder."""

from __future__ import annotations

from typing import Any


def build_audit_summary(job_diagnostics: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(job_diagnostics or {})
    section_statuses = diagnostics.get("section_statuses", {})
    source_availability = diagnostics.get("source_availability", {})

    return {
        "mode": diagnostics.get("mode"),
        "input_path": diagnostics.get("input_path"),
        "partial_flag": bool(diagnostics.get("partial_flag", False)),
        "warnings_count": int(diagnostics.get("warnings_count", 0)),
        "sources_total": len(source_availability) if isinstance(source_availability, dict) else 0,
        "sources_missing": list(diagnostics.get("missing_sources", [])),
        "files_detected_count": len(diagnostics.get("detected_files", {})),
        "files_missing_expected": list(diagnostics.get("missing_expected_files", [])),
        "sections_total": len(section_statuses) if isinstance(section_statuses, dict) else 0,
        "sections_partial": [
            name
            for name, status in (section_statuses.items() if isinstance(section_statuses, dict) else [])
            if str(status) == "partial"
        ],
        "decision_counts_by_priority": dict(diagnostics.get("decision_counts_by_priority", {})),
        "artifacts_written": bool(diagnostics.get("output_artifact_paths")),
        "audit_disclaimer": diagnostics.get("audit_disclaimer"),
    }

