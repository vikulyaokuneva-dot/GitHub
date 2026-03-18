"""Source policy primitives.

Input: source statuses/flags from ingestion and metrics layers.
Output: normalized source labels and helper checks.
Does not fetch data and does not calculate KPI values.
"""

from __future__ import annotations

SOURCE_API = "api"
SOURCE_FILE = "file"
SOURCE_FALLBACK = "fallback"
SOURCE_UNKNOWN = "unknown"

KNOWN_SOURCES = {SOURCE_API, SOURCE_FILE, SOURCE_FALLBACK, SOURCE_UNKNOWN}


def normalize_source(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token in KNOWN_SOURCES:
        return token
    return SOURCE_UNKNOWN
