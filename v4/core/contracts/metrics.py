"""Metrics contracts.

Input: NormalizedBundle.
Output: MetricsBundle.
Does not render output and does not decide actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .raw import RunContext, SourceStatus


@dataclass(frozen=True)
class MetricValue:
    """Typed metric value with provenance.

    Rule: value=None means missing/insufficient and must not be converted to 0.
    """

    value: Optional[float]
    status: str
    source: str
    note: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricsBundle:
    """Top-level metrics payload for downstream layers."""

    context: RunContext
    sections: Dict[str, Dict[str, MetricValue]] = field(default_factory=dict)
    source_status: Dict[str, SourceStatus] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
