"""Daily API mode contract.

Input: none (static mode description).
Output: mode capabilities and source requirements.
Does not execute ingestion.
"""

from __future__ import annotations

MODE_NAME = "daily_api_mode"
REQUIRED_SOURCES = ("orders_api", "sales_api", "realization_api")
OPTIONAL_SOURCES = ("ads_api", "stocks_api", "funnel_api")
AVAILABLE_BLOCKS = (
    "key_metrics",
    "financial",
    "funnel",
    "ads",
    "stock",
    "decisions",
)


def describe() -> dict:
    return {
        "mode": MODE_NAME,
        "required_sources": list(REQUIRED_SOURCES),
        "optional_sources": list(OPTIONAL_SOURCES),
        "available_blocks": list(AVAILABLE_BLOCKS),
    }
