"""Normalized contracts.

Input: RawBundle.
Output: NormalizedBundle with canonical records.
Does not compute business metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .raw import RunContext, SourceStatus


@dataclass
class NormalizedRecord:
    """Generic normalized record envelope."""

    record_type: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedBundle:
    """Canonical records grouped by contour.

    Rule: None values from raw layer remain None unless explicitly transformed.
    """

    context: RunContext
    records: dict[str, list[NormalizedRecord]] = field(default_factory=dict)
    source_status: dict[str, SourceStatus] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def run_context(self) -> RunContext:
        """Alias for consistency with raw/report contracts."""

        return self.context
