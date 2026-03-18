"""Normalized record contracts.

Input: RawBundle.
Output: NormalizedBundle with canonical records.
Does not compute business metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .raw import RunContext, SourceStatus


@dataclass
class NormalizedRecord:
    """Generic normalized record placeholder."""

    record_type: str
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedBundle:
    """Canonical records grouped by contour."""

    context: RunContext
    records: Dict[str, List[NormalizedRecord]] = field(default_factory=dict)
    source_status: Dict[str, SourceStatus] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
