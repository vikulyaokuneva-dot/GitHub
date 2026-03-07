from __future__ import annotations

import re
from typing import Any, Dict, List


_INVALID_VALUES = {"", "0", "none", "null", "nan"}


def normalize_sku(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    if text.lower() in _INVALID_VALUES:
        return None

    compact = text.replace(" ", "")
    # Common Excel artifacts: numeric cell rendered as "123456789.0"
    if re.fullmatch(r"\d+(\.0+)?", compact):
        digits = compact.split(".", 1)[0]
    elif re.fullmatch(r"\d+", compact):
        digits = compact
    else:
        return None

    if digits in {"", "0"}:
        return None
    if not (6 <= len(digits) <= 12):
        return None
    return digits


def is_valid_sku(value: Any) -> bool:
    return normalize_sku(value) is not None


def split_assigned_vs_unassigned_rows(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    assigned: List[Dict[str, Any]] = []
    unassigned: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = normalize_sku(row.get("sku"))
        if sku is None:
            unassigned.append(dict(row))
            continue
        item = dict(row)
        item["sku"] = sku
        assigned.append(item)

    return {"assigned": assigned, "unassigned": unassigned}
