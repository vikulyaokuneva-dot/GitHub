from __future__ import annotations

from typing import Any, Iterable, Mapping


def to_float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    token = text.lower()
    if token in {"none", "null", "nan", "-", "n/a", "na"}:
        return None
    candidate = text.replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None


def to_int_or_none(value: Any) -> int | None:
    parsed = to_float_or_none(value)
    if parsed is None:
        return None
    return int(round(parsed))


def safe_div(numerator: Any, denominator: Any) -> float | None:
    num = to_float_or_none(numerator)
    den = to_float_or_none(denominator)
    if num is None or den is None or den <= 0:
        return None
    return round(num / den, 6)


def safe_round(value: Any, digits: int = 6) -> float | None:
    parsed = to_float_or_none(value)
    if parsed is None:
        return None
    return round(float(parsed), int(digits))


def pick_first(row: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    lookup = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        if alias in row:
            return row.get(alias)
        lowered = str(alias).strip().lower()
        if lowered in lookup:
            return lookup.get(lowered)
    return None


def merge_thresholds(defaults: Mapping[str, float], overrides: Mapping[str, Any] | None) -> dict[str, float]:
    out = {str(k): float(v) for k, v in defaults.items()}
    if not isinstance(overrides, Mapping):
        return out
    for key, fallback in out.items():
        parsed = to_float_or_none(overrides.get(key))
        if parsed is None:
            out[key] = float(fallback)
        else:
            out[key] = float(parsed)
    return out


def append_warning_once(bucket: list[dict[str, Any]], code: str, message: str) -> None:
    normalized = str(code or "").strip()
    if not normalized:
        return
    for item in bucket:
        if isinstance(item, dict) and str(item.get("code") or "").strip() == normalized:
            return
    bucket.append({"code": normalized, "message": str(message or "").strip()})

