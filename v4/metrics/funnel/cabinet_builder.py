"""Funnel cabinet helper.

Input: NormalizedBundle.
Output: run-level list of funnel records for current context.
Does not compute KPI values.
"""

from __future__ import annotations

from ...core.contracts import NormalizedBundle, NormalizedFunnelRecord


def build_run_funnel_records(normalized_bundle: NormalizedBundle) -> list[NormalizedFunnelRecord]:
    """Return funnel records for current run context.

    Stage 6 keeps this helper intentionally thin as extension point for future
    cabinet segmentation logic.
    """

    return list(normalized_bundle.funnel)


def build(payload: NormalizedBundle | None = None) -> list[NormalizedFunnelRecord]:
    """Back-compat alias for stage-1 naming."""

    if payload is None:
        return []
    return build_run_funnel_records(payload)
