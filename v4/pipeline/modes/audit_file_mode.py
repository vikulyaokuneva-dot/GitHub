"""Audit file mode descriptor.

Input: none.
Output: static mode capabilities and source requirements.
Does not execute file parsing.
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
    mode=RunMode.AUDIT_FILE,
    required_sources=("daily_file",),
    optional_sources=("funnel_file", "ads_file", "stocks_file"),
    available_blocks=("raw_ingestion", "diagnostics"),
)


def describe() -> dict[str, object]:
    return {
        "mode": MODE_DESCRIPTOR.mode.value,
        "required_sources": list(MODE_DESCRIPTOR.required_sources),
        "optional_sources": list(MODE_DESCRIPTOR.optional_sources),
        "available_blocks": list(MODE_DESCRIPTOR.available_blocks),
    }
