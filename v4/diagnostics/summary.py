"""Run summary builder for finalized diagnostics.

Input: job diagnostics dictionary.
Output: compact summary dictionary.
Does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any


def build_job_summary(job_diagnostics: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(job_diagnostics or {})
    source_availability = diagnostics.get("source_availability", {})
    section_statuses = diagnostics.get("section_statuses", {})

    return {
        "mode": diagnostics.get("mode"),
        "partial_flag": bool(diagnostics.get("partial_flag", False)),
        "warnings_count": int(diagnostics.get("warnings_count", 0)),
        "sources_total": len(source_availability) if isinstance(source_availability, dict) else 0,
        "sources_missing": list(diagnostics.get("missing_sources", [])),
        "sections_total": len(section_statuses) if isinstance(section_statuses, dict) else 0,
        "sections_partial": [
            name
            for name, status in (section_statuses.items() if isinstance(section_statuses, dict) else [])
            if str(status) == "partial"
        ],
        "decision_counts_by_priority": dict(diagnostics.get("decision_counts_by_priority", {})),
        "artifacts_written": bool(diagnostics.get("output_artifact_paths")),
    }

