"""Daily API mode descriptor.

Input: none.
Output: static mode capabilities and source requirements.
Does not execute ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.contracts import RunMode


@dataclass(frozen=True)
class ModeDescriptor:
    """Declarative mode profile used by orchestration layers."""

    mode: RunMode
    required_sources: tuple[str, ...]
    optional_sources: tuple[str, ...]
    available_blocks: tuple[str, ...]


MODE_DESCRIPTOR = ModeDescriptor(
    mode=RunMode.DAILY_API,
    required_sources=("orders", "sales", "realization"),
    optional_sources=("stocks", "ads", "funnel"),
    available_blocks=(
        "raw_ingestion",
        "normalization",
        "metrics",
        "facts",
        "decisions",
        "outputs",
        "diagnostics",
    ),
)


def describe() -> dict[str, object]:
    return {
        "mode": MODE_DESCRIPTOR.mode.value,
        "required_sources": list(MODE_DESCRIPTOR.required_sources),
        "optional_sources": list(MODE_DESCRIPTOR.optional_sources),
        "available_blocks": list(MODE_DESCRIPTOR.available_blocks),
    }
