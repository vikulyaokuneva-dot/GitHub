"""Decisions contracts.

Input: FactsBundle.
Output: DecisionsBundle.
Does not render PDF/email.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .raw import RunContext


class DecisionPriority(str, Enum):
    """Decision priority levels for rule outcomes."""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class DecisionStatus(str, Enum):
    """Decision status based on evidence quality."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    INFO = "info"


@dataclass(frozen=True)
class DecisionItem:
    """One rule-based decision item with transparent evidence trail."""

    code: str
    title: str
    summary: str
    priority: DecisionPriority
    status: DecisionStatus
    section: str
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionsBundle:
    """Decision payload for downstream report assembly."""

    run_context: RunContext
    items: list[DecisionItem] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> RunContext:
        """Back-compat alias for stage-1 skeleton code."""

        return self.run_context

