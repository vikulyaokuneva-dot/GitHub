from __future__ import annotations

from typing import Any

UNKNOWN_LABEL_RU = "не подтверждено"
DASH_LABEL = "—"


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def format_int_or_unknown(value: Any, *, unknown_label: str = UNKNOWN_LABEL_RU) -> str:
    if value is None:
        return unknown_label
    return f"{_safe_int(value):,}".replace(",", " ")


def format_money_or_unknown(
    value: Any,
    *,
    unknown_label: str = UNKNOWN_LABEL_RU,
    decimals: int = 2,
) -> str:
    if value is None:
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
    if value is None:
        return unknown_label
    return f"{_safe_float(value):.{decimals}f} %"
