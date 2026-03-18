"""Raw ingestion contracts.

Input: run context and source payload statuses.
Output: RawBundle with unmodified payloads.
Does not normalize records and does not compute any KPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RunContext:
    """Execution context shared by all v4 layers."""

    seller_id: str
    mode: str
    requested_date: str
    resolved_date: str
    timezone: str


@dataclass(frozen=True)
class SourceStatus:
    """Availability and quality state of one source."""

    source: str
    status: str
    reason: Optional[str] = None
    rows: Optional[int] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RawBundle:
    """Container for raw source payloads.

    Rule: missing values are represented as None or absent fields.
    Rule: None is not equal to numeric zero.
    """

    context: RunContext
    source_status: Dict[str, SourceStatus] = field(default_factory=dict)
    payloads: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
