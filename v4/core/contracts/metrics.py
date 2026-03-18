"""Metrics contracts.

Input: NormalizedBundle.
Output: MetricsBundle.
Does not render outputs and does not make decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .raw import RunContext, SourceKind, SourceStatus


@dataclass(frozen=True)
class MetricValue:
    """Typed metric value with provenance.

    Rule: value=None means missing/insufficient and must not be converted to 0.
    """

    value: float | int | None
    status: str
    source: SourceKind
    note: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricsBundle:
    """Top-level metrics payload for downstream layers."""

    context: RunContext
    sections: dict[str, dict[str, MetricValue]] = field(default_factory=dict)
    source_status: dict[str, SourceStatus] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def run_context(self) -> RunContext:
        """Alias for consistency with raw/report contracts."""

        return self.context
