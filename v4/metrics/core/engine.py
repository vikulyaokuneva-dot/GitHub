"""Metrics engine skeleton.

Input: NormalizedBundle.
Output: MetricsBundle.
Does not build facts and does not decide actions.
"""

from __future__ import annotations

from ...core.contracts import MetricsBundle, NormalizedBundle


def build_metrics(bundle: NormalizedBundle) -> MetricsBundle:
    return MetricsBundle(
        context=bundle.context,
        sections={
            "financial": {},
            "funnel": {},
            "ads": {},
            "stock": {},
        },
        source_status=bundle.source_status,
        diagnostics={"status": "not_implemented", "stage": "skeleton"},
    )
