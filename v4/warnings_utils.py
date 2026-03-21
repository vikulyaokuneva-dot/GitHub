"""Warning text normalization and deduplication helpers.

Input: arbitrary warning-like values from stages.
Output: normalized, namespaced, deduplicated warning strings.
Does not perform business KPI calculations.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_PREFIX_HEAD = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.+)$", flags=re.IGNORECASE)
_KNOWN_NAMESPACES = {
    "orders",
    "sales",
    "realization",
    "stocks",
    "stock",
    "funnel",
    "ads",
    "ads_campaigns",
    "ads_stats",
    "financial",
    "daily",
    "health",
    "data_quality",
    "email",
    "pdf",
}


def normalize_warning(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = " ".join(text.split())
    head = _PREFIX_HEAD.match(text)
    if head:
        prefix = str(head.group(1) or "").strip()
        remainder = str(head.group(2) or "").strip()
        if prefix and remainder:
            repeated = re.compile(rf"^\s*{re.escape(prefix)}\s*:\s*(.+)$", flags=re.IGNORECASE)
            while True:
                nested = repeated.match(remainder)
                if not nested:
                    break
                remainder = str(nested.group(1) or "").strip()
            text = f"{prefix}: {remainder}"
    return text


def namespace_warning(namespace: str, value: object) -> str:
    text = normalize_warning(value)
    ns = str(namespace or "").strip().lower()
    if not text or not ns:
        return text
    lower = text.lower()
    if lower.startswith(f"{ns}:"):
        return text
    first_token = text.split(":", 1)[0].strip().lower()
    if first_token in _KNOWN_NAMESPACES:
        return text
    return f"{ns}: {text}"


def dedupe_warnings(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = normalize_warning(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def append_warning(target: list[str], value: object, *, namespace: str | None = None) -> None:
    text = namespace_warning(namespace, value) if namespace else normalize_warning(value)
    if text:
        target.append(text)


def extend_warnings(target: list[str], values: Iterable[object], *, namespace: str | None = None) -> None:
    for value in values:
        append_warning(target, value, namespace=namespace)
