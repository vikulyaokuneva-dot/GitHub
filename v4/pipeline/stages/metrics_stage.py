"""Metrics stage for v4 pipeline.

Input: NormalizedBundle.
Output: MetricsBundle.
Does not execute facts/decisions/output stages.
"""

from __future__ import annotations

from ...core.contracts import MetricsBundle, NormalizedBundle
from ...metrics.core.engine import build_metrics_bundle


def run(normalized_bundle: NormalizedBundle) -> MetricsBundle:
    if not isinstance(normalized_bundle, NormalizedBundle):
        raise TypeError("metrics_stage.run expects NormalizedBundle")
    return build_metrics_bundle(normalized_bundle)
