"""Decisions stage for v4 pipeline.

Input: FactsBundle.
Output: DecisionsBundle.
Does not execute output/render stages.
"""

from __future__ import annotations

from ...core.contracts import DecisionsBundle, FactsBundle
from ...decisions.builder import build_decisions_bundle


def run(facts_bundle: FactsBundle) -> DecisionsBundle:
    if not isinstance(facts_bundle, FactsBundle):
        raise TypeError("decisions_stage.run expects FactsBundle")
    return build_decisions_bundle(facts_bundle)

