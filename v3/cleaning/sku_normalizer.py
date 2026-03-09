from __future__ import annotations

import re
from typing import Any, Dict, List


_INVALID_VALUES = {"", "0", "none", "null", "nan"}


def normalize_sku_with_reason(value: Any) -> tuple[str | None, str]:
    if value is None:
        return None, "empty"

    text = str(value).strip()
    if not text:
        return None, "empty"
    if text.lower() in _INVALID_VALUES:
        return None, "invalid_literal"

    compact = text.replace(" ", "")
    # Common Excel artifacts: numeric cell rendered as "123456789.0"
    if re.fullmatch(r"\d+(\.0+)?", compact):
        digits = compact.split(".", 1)[0]
    elif re.fullmatch(r"\d+", compact):
        digits = compact
    else:
        return None, "contains_non_digits"

    if digits in {"", "0"}:
        return None, "zero_value"
    if not (6 <= len(digits) <= 12):
        return None, "length_out_of_range"
    return digits, "ok"


def normalize_sku(value: Any) -> str | None:
    normalized, _ = normalize_sku_with_reason(value)
    return normalized


def is_valid_sku(value: Any) -> bool:
    return normalize_sku(value) is not None


def split_assigned_vs_unassigned_rows(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    assigned: List[Dict[str, Any]] = []
    unassigned: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        sku, reason = normalize_sku_with_reason(row.get("sku"))
        if sku is None:
            item = dict(row)
            item["_is_valid_sku"] = False
            item["_sku_validation_reason"] = reason
            unassigned.append(item)
            continue
        item = dict(row)
        item["sku"] = sku
        item["_is_valid_sku"] = True
        item["_sku_validation_reason"] = reason
        assigned.append(item)

    return {"assigned": assigned, "unassigned": unassigned}
