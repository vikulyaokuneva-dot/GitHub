"""Static WB warehouses logistics coefficients reference helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHEAP_THRESHOLD = 100.0
EXPENSIVE_THRESHOLD = 130.0
HIGH_COEFFICIENT_ALERT = 150.0

DEFAULT_REFERENCE_PATH = (
    Path(__file__).resolve().parent / "data" / "warehouse_logistics_coefficients.json"
)


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _norm_key(text: Any) -> str:
    value = str(text or "")
    return " ".join(value.replace("\xa0", " ").strip().lower().split())


def load_warehouse_logistics_reference(
    path: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    target = Path(path) if path is not None else DEFAULT_REFERENCE_PATH
    with target.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    result: dict[str, list[dict[str, Any]]] = {}
    for region, entries in (raw or {}).items():
        region_name = str(region or "").strip()
        if not region_name:
            continue
        dedup: set[str] = set()
        region_rows: list[dict[str, Any]] = []
        for item in entries or []:
            if not isinstance(item, dict):
                continue
            warehouse = str(item.get("warehouse") or "").strip()
            if not warehouse:
                continue
            key = _norm_key(warehouse)
            if key in dedup:
                continue
            dedup.add(key)
            region_rows.append(
                {
                    "warehouse": warehouse,
                    "coefficient": _to_float_or_none(item.get("coefficient")),
                }
            )
        result[region_name] = region_rows
    return result


def flatten_warehouse_logistics_reference(
    reference: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    source = reference if reference is not None else load_warehouse_logistics_reference()
    rows: list[dict[str, Any]] = []
    for region, entries in source.items():
        for item in entries or []:
            rows.append(
                {
                    "region": str(region or "").strip(),
                    "warehouse": str((item or {}).get("warehouse") or "").strip(),
                    "coefficient": _to_float_or_none((item or {}).get("coefficient")),
                }
            )
    return rows


def classify_region_logistics(
    avg_coefficient: float | None,
    *,
    cheap_threshold: float = CHEAP_THRESHOLD,
    expensive_threshold: float = EXPENSIVE_THRESHOLD,
) -> str:
    if avg_coefficient is None:
        return "unknown"
    if avg_coefficient < cheap_threshold:
        return "cheap"
    if avg_coefficient <= expensive_threshold:
        return "normal"
    return "expensive"


def build_region_logistics_summary(
    reference: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, dict[str, Any]]:
    source = reference if reference is not None else load_warehouse_logistics_reference()
    summary: dict[str, dict[str, Any]] = {}
    for region, entries in source.items():
        values = [
            _to_float_or_none((item or {}).get("coefficient"))
            for item in (entries or [])
        ]
        known = [float(x) for x in values if x is not None]
        unknown_count = sum(1 for x in values if x is None)
        avg = round(sum(known) / len(known), 1) if known else None
        summary[region] = {
            "known_count": int(len(known)),
            "unknown_count": int(unknown_count),
            "min_coefficient": round(min(known), 1) if known else None,
            "max_coefficient": round(max(known), 1) if known else None,
            "avg_coefficient": avg,
            "class": classify_region_logistics(avg),
        }
    return summary


__all__ = [
    "CHEAP_THRESHOLD",
    "EXPENSIVE_THRESHOLD",
    "HIGH_COEFFICIENT_ALERT",
    "DEFAULT_REFERENCE_PATH",
    "load_warehouse_logistics_reference",
    "flatten_warehouse_logistics_reference",
    "build_region_logistics_summary",
    "classify_region_logistics",
]
