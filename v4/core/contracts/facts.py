"""Facts contracts.

Input: MetricsBundle.
Output: FactsBundle.
Does not recalculate KPI formulas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from .raw import RunContext, SourceStatus


@dataclass
class FactsBundle:
    """Facts payload used by decisions and reporting layers."""

    context: RunContext
    finance: Dict[str, Any] = field(default_factory=dict)
    funnel: Dict[str, Any] = field(default_factory=dict)
    ads: Dict[str, Any] = field(default_factory=dict)
    stock: Dict[str, Any] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    source_status: Dict[str, SourceStatus] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
