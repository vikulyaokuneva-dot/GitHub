from __future__ import annotations

import math
from typing import Any

UNKNOWN_LABEL_RU = "недостаточно данных"
DASH_LABEL = "—"
SECTION_STATE_FULL = "full"
SECTION_STATE_PARTIAL = "partial"
SECTION_STATE_COMPACT_NOTE = "compact_note"
SECTION_STATE_HIDDEN = "hidden"

_VALID_SECTION_STATES = {
    SECTION_STATE_FULL,
    SECTION_STATE_PARTIAL,
    SECTION_STATE_COMPACT_NOTE,
    SECTION_STATE_HIDDEN,
}

_MISSING_LITERALS = {
    "",
    "none",
    "null",
    "nan",
    "unknown",
    "not_confirmed",
    "n/a",
    "na",
    "-",
}


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, str):
        return value.strip().lower() in _MISSING_LITERALS
    return False


def normalize_section_state(value: Any, *, default: str = SECTION_STATE_HIDDEN) -> str:
    token = str(value or "").strip().lower()
    if token in _VALID_SECTION_STATES:
        return token
    return default if default in _VALID_SECTION_STATES else SECTION_STATE_HIDDEN


def build_section_display_state(
    *,
    has_full_data: bool,
    has_partial_data: bool = False,
    note: str = "",
    allow_hidden: bool = True,
) -> dict[str, str]:
    clean_note = str(note or "").strip()
    if has_full_data:
        state = SECTION_STATE_FULL
    elif has_partial_data:
        state = SECTION_STATE_PARTIAL
    elif clean_note:
        state = SECTION_STATE_COMPACT_NOTE
    else:
        state = SECTION_STATE_HIDDEN if allow_hidden else SECTION_STATE_COMPACT_NOTE
    return {
        "state": state,
        "note": clean_note if state in {SECTION_STATE_PARTIAL, SECTION_STATE_COMPACT_NOTE} else "",
    }


def build_kpi_display_payload(
    *,
    value: Any,
    fallback_value: Any = None,
    missing_reason: str = "",
    label: str = "",
    fallback_label: str | None = None,
    value_type: str = "int",
) -> dict[str, Any]:
    clean_label = str(label or "").strip()
    clean_fallback_label = str(fallback_label or clean_label).strip()
    clean_reason = str(missing_reason or "").strip()
    if not is_missing_value(value):
        state = SECTION_STATE_FULL
        payload_value = value
        payload_label = clean_label
        source = "primary"
    elif not is_missing_value(fallback_value):
        state = SECTION_STATE_PARTIAL
        payload_value = fallback_value
        payload_label = clean_fallback_label
        source = "fallback"
    elif clean_reason:
        state = SECTION_STATE_COMPACT_NOTE
        payload_value = None
        payload_label = clean_label
        source = "missing"
    else:
        state = SECTION_STATE_HIDDEN
        payload_value = None
        payload_label = clean_label
        source = "missing"
    return {
        "state": state,
        "label": payload_label,
        "base_label": clean_label,
        "value": payload_value,
        "value_type": str(value_type or "int").strip().lower() or "int",
        "reason": clean_reason if state in {SECTION_STATE_PARTIAL, SECTION_STATE_COMPACT_NOTE} else "",
        "source": source,
        "is_fallback": bool(state == SECTION_STATE_PARTIAL and source == "fallback"),
    }


def _safe_float(value: Any) -> float:
    try:
        if is_missing_value(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if is_missing_value(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def format_int_or_unknown(value: Any, *, unknown_label: str = UNKNOWN_LABEL_RU) -> str:
    if is_missing_value(value):
        return unknown_label
    return f"{_safe_int(value):,}".replace(",", " ")


def format_money_or_unknown(
    value: Any,
    *,
    unknown_label: str = UNKNOWN_LABEL_RU,
    decimals: int = 2,
) -> str:
    if is_missing_value(value):
        return unknown_label
    amount = _safe_float(value)
    if decimals <= 0:
        rounded = int(round(amount))
        return f"{rounded:,}".replace(",", " ")
    return f"{amount:,.{decimals}f}".replace(",", " ")


def format_pct_or_unknown(
    value: Any,
    *,
    unknown_label: str = UNKNOWN_LABEL_RU,
    decimals: int = 1,
) -> str:
    if is_missing_value(value):
        return unknown_label
    return f"{_safe_float(value):.{decimals}f} %"

