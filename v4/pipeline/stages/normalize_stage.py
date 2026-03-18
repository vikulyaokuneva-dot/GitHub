"""Normalize stage for v4.

Input: RawBundle or IngestionResult.
Output: NormalizedBundle.
Does not compute metrics/facts or render outputs.
"""

from __future__ import annotations

from ...core.contracts import IngestionResult, NormalizedBundle, RawBundle
from ...normalization.normalizers import build_normalized_bundle


def run(input_payload: RawBundle | IngestionResult) -> NormalizedBundle:
    if isinstance(input_payload, IngestionResult):
        raw_bundle = input_payload.raw_bundle
    elif isinstance(input_payload, RawBundle):
        raw_bundle = input_payload
    else:
        raise TypeError("normalize_stage.run expects RawBundle or IngestionResult")

    return build_normalized_bundle(raw_bundle)
