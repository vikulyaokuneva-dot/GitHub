"""Shadow-mode comparator between v4 result and optional legacy result.

Comparator only reads already-computed outputs/facts/decisions/summary and does not
recompute KPI.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .contracts import ShadowComparison, ShadowDifference


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        try:
            return _to_plain(getattr(value, "value"))
        except Exception:
            return value
    return value


def _extract_payloads(result: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if result is None:
        return ({}, {}, {})
    plain = _to_plain(result)
    if not isinstance(plain, dict):
        return ({}, {}, {})

    outputs = plain.get("outputs", {})
    artifacts = outputs.get("artifacts", {}) if isinstance(outputs, dict) else {}
    payloads = artifacts.get("payloads", {}) if isinstance(artifacts, dict) else {}
    if isinstance(payloads, dict):
        facts = payloads.get("facts", {}) if isinstance(payloads.get("facts"), dict) else {}
        decisions = payloads.get("decisions", {}) if isinstance(payloads.get("decisions"), dict) else {}
        summary = payloads.get("outputs_summary", {}) if isinstance(payloads.get("outputs_summary"), dict) else {}
        if facts or decisions or summary:
            return (facts, decisions, summary)

    facts = plain.get("facts", {}) if isinstance(plain.get("facts"), dict) else {}
    decisions = plain.get("decisions", {}) if isinstance(plain.get("decisions"), dict) else {}
    summary = {}
    diagnostics = plain.get("diagnostics", {}) if isinstance(plain.get("diagnostics"), dict) else {}
    summary_payload = diagnostics.get("summary", {}) if isinstance(diagnostics.get("summary"), dict) else {}
    if summary_payload:
        summary = dict(summary_payload)
    return (facts, decisions, summary)


def _fact_value(facts_payload: dict[str, Any], section_name: str, key: str) -> Any:
    sections = facts_payload.get("sections", {})
    if isinstance(sections, dict):
        section = sections.get(section_name, {})
        items = section.get("items", []) if isinstance(section, dict) else []
    elif isinstance(sections, list):
        items = []
        for section in sections:
            if isinstance(section, dict) and section.get("section_name") == section_name:
                items = section.get("items", [])
                break
    else:
        items = []

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("key") != key:
                continue
            value = item.get("value", {})
            if isinstance(value, dict):
                return value.get("value")
            return value
    return None


def _decision_counts(decisions_payload: dict[str, Any]) -> dict[str, int]:
    summary = decisions_payload.get("summary", {})
    if isinstance(summary, dict):
        by_priority = summary.get("by_priority", {})
        if isinstance(by_priority, dict):
            return {
                "P1": int(by_priority.get("P1", 0) or 0),
                "P2": int(by_priority.get("P2", 0) or 0),
                "P3": int(by_priority.get("P3", 0) or 0),
            }

    items = decisions_payload.get("items", [])
    counts = {"P1": 0, "P2": 0, "P3": 0}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            priority = str(item.get("priority", "")).strip()
            if priority in counts:
                counts[priority] += 1
    return counts


def _decision_codes(decisions_payload: dict[str, Any]) -> list[str]:
    summary = decisions_payload.get("summary", {})
    if isinstance(summary, dict):
        codes = summary.get("decision_codes")
        if isinstance(codes, list):
            return sorted([str(code) for code in codes])
    items = decisions_payload.get("items", [])
    if isinstance(items, list):
        return sorted([str(item.get("code")) for item in items if isinstance(item, dict) and item.get("code") is not None])
    return []


def _summary_partial_flag(summary_payload: dict[str, Any]) -> bool | None:
    if not isinstance(summary_payload, dict):
        return None
    if "partial_flag" not in summary_payload:
        return None
    return bool(summary_payload.get("partial_flag"))


def _summary_warnings_count(summary_payload: dict[str, Any]) -> int | None:
    if not isinstance(summary_payload, dict):
        return None
    value = summary_payload.get("warnings_count")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _metric_severity(metric_name: str, v4_value: Any, legacy_value: Any) -> str | None:
    if v4_value is None or legacy_value is None:
        return None
    v4_num = _to_float(v4_value)
    legacy_num = _to_float(legacy_value)
    if v4_num is None or legacy_num is None:
        return "medium" if str(v4_value) != str(legacy_value) else None

    diff = abs(v4_num - legacy_num)
    baseline = max(abs(legacy_num), 1.0)
    ratio = diff / baseline

    if metric_name in {"revenue", "net_profit_like"}:
        if diff >= 1000 and ratio >= 0.2:
            return "high"
        if diff >= 200 and ratio >= 0.1:
            return "medium"
    if metric_name in {"margin", "total_stock_units", "out_of_stock_items"}:
        if diff >= 100 and ratio >= 0.2:
            return "high"
        if diff >= 10 and ratio >= 0.1:
            return "medium"
    return "low" if diff > 0 else None


def _append_difference(
    differences: list[ShadowDifference],
    *,
    metric: str,
    v4_value: Any,
    legacy_value: Any,
) -> None:
    severity = _metric_severity(metric, v4_value, legacy_value)
    if severity is None:
        return
    differences.append(
        ShadowDifference(
            metric=metric,
            v4_value=v4_value,
            legacy_value=legacy_value,
            severity=severity,
            note="value mismatch",
        )
    )


def _overall_severity(differences: list[ShadowDifference], *, partial_context: bool) -> str:
    if not differences:
        return "low"
    severities = {item.severity for item in differences}
    if partial_context and "high" in severities:
        return "medium"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def compare_results(v4_result: Any, legacy_result: Any) -> dict[str, Any]:
    if legacy_result is None:
        return ShadowComparison(
            differences=[],
            severity="low",
            notes=["legacy result is not available; comparison is informational only"],
        ).to_dict()

    v4_facts, v4_decisions, v4_summary = _extract_payloads(v4_result)
    legacy_facts, legacy_decisions, legacy_summary = _extract_payloads(legacy_result)

    if not legacy_facts and not legacy_decisions and not legacy_summary:
        return ShadowComparison(
            differences=[],
            severity="low",
            notes=["legacy payload shape is unsupported or empty; strict comparison skipped"],
        ).to_dict()

    differences: list[ShadowDifference] = []
    notes: list[str] = []

    finance_pairs = {
        "revenue": (
            _fact_value(v4_facts, "financial", "revenue_gross"),
            _fact_value(legacy_facts, "financial", "revenue_gross"),
        ),
        "net_profit_like": (
            _fact_value(v4_facts, "financial", "net_profit_like"),
            _fact_value(legacy_facts, "financial", "net_profit_like"),
        ),
        "margin": (
            _fact_value(v4_facts, "financial", "margin"),
            _fact_value(legacy_facts, "financial", "margin"),
        ),
    }
    for metric, (v4_value, legacy_value) in finance_pairs.items():
        _append_difference(differences, metric=metric, v4_value=v4_value, legacy_value=legacy_value)
        if v4_value is None or legacy_value is None:
            notes.append(f"{metric}: one side is missing or unavailable")

    stock_pairs = {
        "total_stock_units": (
            _fact_value(v4_facts, "stock", "total_stock_units"),
            _fact_value(legacy_facts, "stock", "total_stock_units"),
        ),
        "out_of_stock_items": (
            _fact_value(v4_facts, "stock", "out_of_stock_items_count"),
            _fact_value(legacy_facts, "stock", "out_of_stock_items_count"),
        ),
    }
    for metric, (v4_value, legacy_value) in stock_pairs.items():
        _append_difference(differences, metric=metric, v4_value=v4_value, legacy_value=legacy_value)
        if v4_value is None or legacy_value is None:
            notes.append(f"{metric}: one side is missing or unavailable")

    v4_counts = _decision_counts(v4_decisions)
    legacy_counts = _decision_counts(legacy_decisions)
    for priority in ("P1", "P2", "P3"):
        _append_difference(
            differences,
            metric=f"decision_count_{priority}",
            v4_value=v4_counts.get(priority),
            legacy_value=legacy_counts.get(priority),
        )

    v4_codes = _decision_codes(v4_decisions)
    legacy_codes = _decision_codes(legacy_decisions)
    if v4_codes and legacy_codes and v4_codes != legacy_codes:
        differences.append(
            ShadowDifference(
                metric="decision_codes",
                v4_value=v4_codes,
                legacy_value=legacy_codes,
                severity="medium",
                note="decision code sets differ",
            )
        )
    elif not v4_codes or not legacy_codes:
        notes.append("decision code comparison is partial due to missing code lists")

    v4_partial = _summary_partial_flag(v4_summary)
    legacy_partial = _summary_partial_flag(legacy_summary)
    if v4_partial is not None and legacy_partial is not None and v4_partial != legacy_partial:
        differences.append(
            ShadowDifference(
                metric="partial_flag",
                v4_value=v4_partial,
                legacy_value=legacy_partial,
                severity="medium",
                note="data quality partial flags differ",
            )
        )

    v4_warnings = _summary_warnings_count(v4_summary)
    legacy_warnings = _summary_warnings_count(legacy_summary)
    if v4_warnings is not None and legacy_warnings is not None:
        _append_difference(
            differences,
            metric="warnings_count",
            v4_value=v4_warnings,
            legacy_value=legacy_warnings,
        )

    partial_context = bool(v4_partial) or bool(legacy_partial)
    severity = _overall_severity(differences, partial_context=partial_context)

    if partial_context:
        notes.append("partial context detected; severe differences are down-weighted for shadow review")
    if not differences:
        notes.append("no significant differences detected")

    return ShadowComparison(differences=differences, severity=severity, notes=notes).to_dict()


__all__ = ["compare_results"]

