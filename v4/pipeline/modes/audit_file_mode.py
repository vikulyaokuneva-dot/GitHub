"""Audit file mode contract.

Input: none (static mode description).
Output: mode capabilities and source requirements.
Does not execute file parsing.
"""

from __future__ import annotations

MODE_NAME = "audit_file_mode"
REQUIRED_SOURCES = ("daily_file",)
OPTIONAL_SOURCES = ("funnel_file", "ads_file", "stocks_file")
AVAILABLE_BLOCKS = (
    "key_metrics",
    "financial",
    "funnel_limited",
    "ads_limited",
    "stock_limited",
    "decisions_limited",
)


def describe() -> dict:
    return {
        "mode": MODE_NAME,
        "required_sources": list(REQUIRED_SOURCES),
        "optional_sources": list(OPTIONAL_SOURCES),
        "available_blocks": list(AVAILABLE_BLOCKS),
    }
