"""Facts contracts.

Input: MetricsBundle.
Output: FactsBundle.
Does not recalculate KPI formulas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .raw import RunContext


@dataclass(frozen=True)
class FactValue:
    """Lightweight fact value wrapper mapped from metrics layer.

    Rule: None remains None and is not converted to 0.
    """

    value: float | int | str | None
    status: str
    source: str | None
    note: str | None = None


@dataclass
class FactItem:
    """Single fact item for section-based facts."""

    key: str
    title: str
    value: FactValue
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class FactSection:
    """Facts grouped by contour."""

    section_name: str
    title: str
    items: list[FactItem] = field(default_factory=list)
    status: str = "unavailable"
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class FactsBundle:
    """Facts payload between metrics and future decisions layer."""

    run_context: RunContext
    sections: dict[str, FactSection] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> RunContext:
        """Back-compat alias for stage-1 skeleton code."""

        return self.run_context

