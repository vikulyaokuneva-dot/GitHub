"""Facts stage for v4 pipeline.

Input: MetricsBundle.
Output: FactsBundle.
Does not execute decisions/output stages.
"""

from __future__ import annotations

from ...core.contracts import FactsBundle, MetricsBundle
from ...outputs.facts.builder import build_facts_bundle


def run(metrics_bundle: MetricsBundle) -> FactsBundle:
    if not isinstance(metrics_bundle, MetricsBundle):
        raise TypeError("facts_stage.run expects MetricsBundle")
    return build_facts_bundle(metrics_bundle)

