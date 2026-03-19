"""Audit-mode summary builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _status_to_text(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value)


def _priority_counts(raw: object) -> dict[str, int]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        "P1": int(payload.get("P1", 0) or 0),
        "P2": int(payload.get("P2", 0) or 0),
        "P3": int(payload.get("P3", 0) or 0),
    }


def _path_label(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Path(text).name or text
    except Exception:
        return text


def build_audit_summary(job_diagnostics: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(job_diagnostics or {})
    section_statuses = diagnostics.get("section_statuses", {})
    source_availability = diagnostics.get("source_availability", {})

    return {
        "mode": diagnostics.get("mode"),
        "input_path": diagnostics.get("input_path"),
        "input_path_label": _path_label(diagnostics.get("input_path")),
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
            if _status_to_text(status) == "partial"
        ],
        "decision_counts_by_priority": _priority_counts(diagnostics.get("decision_counts_by_priority")),
        "artifacts_written": bool(diagnostics.get("output_artifact_paths")),
        "audit_disclaimer": diagnostics.get("audit_disclaimer"),
    }
