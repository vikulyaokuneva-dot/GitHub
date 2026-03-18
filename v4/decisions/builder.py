"""Decisions builder skeleton.

Input: FactsBundle.
Output: DecisionsBundle.
Does not render report sections.
"""

from __future__ import annotations

from ..core.contracts import DecisionsBundle, FactsBundle


def build_decisions(facts: FactsBundle) -> DecisionsBundle:
    return DecisionsBundle(
        context=facts.context,
        items=[],
        summary={"status": "not_implemented", "stage": "skeleton"},
        diagnostics={},
    )
