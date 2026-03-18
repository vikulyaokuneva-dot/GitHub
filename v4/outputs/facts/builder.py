"""Facts output builder skeleton.

Input: MetricsBundle.
Output: FactsBundle.
Does not recalculate KPI.
"""

from __future__ import annotations

from ...core.contracts import FactsBundle, MetricsBundle


def build(metrics: MetricsBundle) -> FactsBundle:
    return FactsBundle(
        context=metrics.context,
        data_quality={"status": "not_implemented", "stage": "skeleton"},
        source_status=metrics.source_status,
        diagnostics=metrics.diagnostics,
    )
