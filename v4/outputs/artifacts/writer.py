"""Artifacts writer for outputs layer.

Input: FactsBundle + DecisionsBundle.
Output: serializable payloads and optional JSON files on disk.
Does not compute KPI and does not read runtime seller folders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ...core.contracts import DecisionsBundle, FactsBundle


AUDIT_DISCLAIMER = "Отчет построен в audit_file_mode; выводы ограничены доступными файлами."


def _normalize_mode(mode: object) -> str:
    return "audit" if str(mode).strip().lower() == "audit" else "daily"


def _to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_serializable(asdict(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(item) for item in value]
    return value


def _decision_counts_by_priority(decisions_bundle: DecisionsBundle) -> dict[str, int]:
    counts: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0}
    for item in decisions_bundle.items:
        key = item.priority.value if hasattr(item.priority, "value") else str(item.priority)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _coverage_kind(*, status_text: str, reason: str) -> str:
    token = str(status_text).strip().lower()
    why = str(reason).strip().lower()
    if why in {"auth_error", "auth_failed", "request_failed", "parse_failed", "normalized_empty"}:
        return "source_failed"
    if why in {"no_data_for_date", "no_realization_in_window"}:
        return "source_unavailable_for_selected_date"
    if token == "missing" and why in {"empty_payload", "ok_empty_payload"}:
        return "source_empty_but_valid"
    if token in {"missing", "not_implemented"}:
        return "source_missing"
    if token == "error":
        return "source_failed"
    if token == "partial":
        return "source_partial"
    return "source_available"


def build_artifact_payloads(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str = "daily",
) -> dict[str, Any]:
    facts_payload = _to_serializable(facts_bundle)
    decisions_payload = _to_serializable(decisions_bundle)

    sections_present = sorted(str(name) for name in facts_bundle.sections.keys())
    warnings_count = len(facts_bundle.warnings) + len(decisions_bundle.warnings)
    partial_flag = bool(facts_bundle.data_quality.get("partial_sections") or facts_bundle.data_quality.get("unavailable_sections"))
    normalized_mode = _normalize_mode(mode)
    source_flags_payload = facts_bundle.data_quality.get("source_flags")
    source_flags = dict(source_flags_payload) if isinstance(source_flags_payload, dict) else {}
    source_reason_payload = facts_bundle.diagnostics.get("source_reason_map")
    source_reason_map = (
        {str(k): str(v) for k, v in source_reason_payload.items()}
        if isinstance(source_reason_payload, dict)
        else {}
    )
    missing_sources = [name for name, status in source_flags.items() if str(status) not in {"ok", "partial"}]
    partial_sources = [
        name
        for name, status in source_flags.items()
        if str(status) == "partial" or str(source_reason_map.get(name, "")).strip().lower() in {"parse_failed", "normalized_empty"}
    ]
    source_coverage_summary = {
        name: _coverage_kind(status_text=str(status), reason=str(source_reason_map.get(name, "")))
        for name, status in source_flags.items()
    }

    outputs_summary = {
        "build_timestamp": None,
        "build_timestamp_note": "deterministic stage: timestamp omitted by design",
        "mode": normalized_mode,
        "seller_id": facts_bundle.run_context.seller_id,
        "cabinet_id": facts_bundle.run_context.cabinet_id,
        "cabinet_name": facts_bundle.run_context.cabinet_name,
        "output_dir_label": facts_bundle.run_context.output_dir,
        "input_path_label": facts_bundle.run_context.input_path_label,
        "feature_flags": dict(facts_bundle.run_context.feature_flags),
        "path_labels": dict(facts_bundle.run_context.path_labels),
        "sections_present": sections_present,
        "decision_counts_by_priority": _decision_counts_by_priority(decisions_bundle),
        "warnings_count": warnings_count,
        "partial_flag": partial_flag,
        "missing_sources": missing_sources,
        "partial_sources": partial_sources,
        "source_reason_map": source_reason_map,
        "source_coverage_summary": source_coverage_summary,
        "audit_note": AUDIT_DISCLAIMER if normalized_mode == "audit" else None,
    }

    return {
        "facts": facts_payload,
        "decisions": decisions_payload,
        "outputs_summary": outputs_summary,
    }


def save_artifact_payloads(payloads: dict[str, Any], output_dir: str) -> dict[str, str]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    file_map = {
        "facts": "facts.json",
        "decisions": "decisions.json",
        "outputs_summary": "outputs_summary.json",
    }

    written: dict[str, str] = {}
    for payload_key, filename in file_map.items():
        target = out_path / filename
        content = _to_serializable(payloads.get(payload_key))
        target.write_text(
            json.dumps(content, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written[payload_key] = str(target)
    return written
