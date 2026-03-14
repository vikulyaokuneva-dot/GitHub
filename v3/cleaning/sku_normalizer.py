from __future__ import annotations

from typing import Any, Dict, List

from ..validation.sku_normalization import normalize_sku_with_reason as _normalize_sku_with_reason
from ..validation.sku_normalization import resolve_row_sku


def normalize_sku_with_reason(value: Any) -> tuple[str | None, str]:
    normalized, reason = _normalize_sku_with_reason(value)
    return normalized, reason


def normalize_sku(value: Any) -> str | None:
    normalized, _ = normalize_sku_with_reason(value)
    return normalized


def is_valid_sku(value: Any) -> bool:
    return normalize_sku(value) is not None


def split_assigned_vs_unassigned_rows(
    rows: List[Dict[str, Any]],
    *,
    dataset_name: str = "",
) -> Dict[str, List[Dict[str, Any]]]:
    assigned: List[Dict[str, Any]] = []
    unassigned: List[Dict[str, Any]] = []
    diagnostics = {
        "dataset": str(dataset_name or ""),
        "rows_total": 0,
        "rows_assigned": 0,
        "rows_unassigned": 0,
        "fallback_sku_rows": 0,
        "source_kind_counts": {"primary": 0, "fallback": 0, "unknown": 0},
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        diagnostics["rows_total"] = int(diagnostics.get("rows_total", 0) or 0) + 1
        resolved = resolve_row_sku(row)
        sku = resolved.get("sku")
        reason = str(resolved.get("reason") or "unknown")
        source_field = str(resolved.get("source_field") or row.get("_sku_source_field") or "")
        source_kind = str(resolved.get("source_kind") or "unknown")
        if source_kind not in diagnostics["source_kind_counts"]:
            diagnostics["source_kind_counts"][source_kind] = 0
        diagnostics["source_kind_counts"][source_kind] = int(diagnostics["source_kind_counts"][source_kind] or 0) + 1
        if bool(resolved.get("fallback_used", False)):
            diagnostics["fallback_sku_rows"] = int(diagnostics.get("fallback_sku_rows", 0) or 0) + 1

        if sku is None:
            item = dict(row)
            item["_is_valid_sku"] = False
            item["_sku_validation_reason"] = reason
            item["_sku_source_field"] = source_field
            item["_sku_source_kind"] = source_kind
            item["_sku_fallback_used"] = bool(resolved.get("fallback_used", False))
            unassigned.append(item)
            diagnostics["rows_unassigned"] = int(diagnostics.get("rows_unassigned", 0) or 0) + 1
            continue

        item = dict(row)
        item["sku"] = sku
        item["_is_valid_sku"] = True
        item["_sku_validation_reason"] = reason
        item["_sku_source_field"] = source_field
        item["_sku_source_kind"] = source_kind
        item["_sku_fallback_used"] = bool(resolved.get("fallback_used", False))
        assigned.append(item)
        diagnostics["rows_assigned"] = int(diagnostics.get("rows_assigned", 0) or 0) + 1

    return {"assigned": assigned, "unassigned": unassigned, "diagnostics": diagnostics}
