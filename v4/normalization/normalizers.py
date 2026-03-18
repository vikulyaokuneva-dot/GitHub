"""Normalizer skeleton.

Input: RawBundle.
Output: NormalizedBundle.
Does not compute metrics and does not render outputs.
"""

from __future__ import annotations

from ..core.contracts import NormalizedBundle, RawBundle


def normalize(raw_bundle: RawBundle) -> NormalizedBundle:
    """Build an empty normalized bundle in stage 1."""
    return NormalizedBundle(
        context=raw_bundle.context,
        records={},
        source_status=raw_bundle.source_status,
        diagnostics={"status": "not_implemented", "stage": "skeleton"},
    )
