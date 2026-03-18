"""Report contracts.

Input: FactsBundle + DecisionsBundle.
Output: ReportPayload for PDF/email generation.
Does not fetch data and does not compute core metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from .raw import RunContext


@dataclass
class ReportPayload:
    """Final payload passed into renderers/transports."""

    context: RunContext
    sections: Dict[str, Any] = field(default_factory=dict)
    status: str = "draft"
    diagnostics: Dict[str, Any] = field(default_factory=dict)
