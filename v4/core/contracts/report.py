"""Report contracts.

Input: FactsBundle + DecisionsBundle.
Output: ReportPayload consumed by renderers/transports.
Does not fetch data and does not compute KPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .raw import RunContext


@dataclass
class ReportPayload:
    """Final report payload.

    Rule: missing values are preserved as None for render policy handling.
    """

    context: RunContext
    sections: dict[str, Any] = field(default_factory=dict)
    status: str = "draft"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def run_context(self) -> RunContext:
        """Alias for consistency with raw contract naming."""

        return self.context
