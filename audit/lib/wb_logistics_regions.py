"""Internal helpers for WB regional logistics coefficients."""

from __future__ import annotations

from typing import Any

from audit.lib.logistics_reference import (
    HIGH_COEFFICIENT_ALERT,
    build_region_logistics_summary,
    load_warehouse_logistics_reference,
)


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def normalize_region_coefficients(
    region_summary: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    source = region_summary if isinstance(region_summary, dict) else {}
    for region, row in source.items():
        if not isinstance(row, dict):
            continue
        out[str(region)] = {
            "known_count": int(row.get("known_count") or 0),
            "unknown_count": int(row.get("unknown_count") or 0),
            "min_pct": _to_float_or_none(row.get("min_coefficient")),
            "max_pct": _to_float_or_none(row.get("max_coefficient")),
            "avg_pct": _to_float_or_none(row.get("avg_coefficient")),
            "class": str(row.get("class") or "unknown"),
        }
    return out


def build_wb_region_coefficients(
    reference: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, dict[str, Any]]:
    source = reference if reference is not None else load_warehouse_logistics_reference()
    region_summary = build_region_logistics_summary(source)
    return normalize_region_coefficients(region_summary)


def high_risk_regions_by_avg(
    region_coefficients: dict[str, dict[str, Any]] | None,
    *,
    threshold_pct: float = HIGH_COEFFICIENT_ALERT,
) -> list[str]:
    out: list[str] = []
    source = region_coefficients if isinstance(region_coefficients, dict) else {}
    for region, row in source.items():
        if not isinstance(row, dict):
            continue
        avg = _to_float_or_none(row.get("avg_pct"))
        if avg is not None and float(avg) > float(threshold_pct):
            out.append(str(region))
    return sorted(out)


__all__ = [
    "normalize_region_coefficients",
    "build_wb_region_coefficients",
    "high_risk_regions_by_avg",
]
