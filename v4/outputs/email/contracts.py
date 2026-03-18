"""Email payload contracts.

Input: FactsBundle + DecisionsBundle.
Output: deterministic plain-text friendly email payload.
Does not send email transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmailSection:
    """Single email section rendered as plain text lines."""

    title: str
    lines: list[str] = field(default_factory=list)
    status: str = "unavailable"


@dataclass
class EmailPayload:
    """Email payload prepared by outputs layer."""

    subject: str
    preheader: str
    mode: str
    summary_lines: list[str] = field(default_factory=list)
    sections: list[EmailSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

