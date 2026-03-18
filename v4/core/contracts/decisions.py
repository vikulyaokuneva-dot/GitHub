"""Decisions contracts.

Input: FactsBundle.
Output: DecisionsBundle.
Does not render PDF/email.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .raw import RunContext


@dataclass(frozen=True)
class DecisionItem:
    """One decision/recommendation unit."""

    priority: str
    title: str
    reason: str
    owner: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionsBundle:
    """Decision payload for report assembly."""

    context: RunContext
    items: List[DecisionItem] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
