"""Metrics assembler facade.

Input: NormalizedBundle.
Output: MetricsBundle.
Does not execute facts/decisions/outputs.
"""

from __future__ import annotations

from ..core.contracts import MetricsBundle, NormalizedBundle
from .core.engine import build_metrics_bundle as _build_metrics_bundle


def build_metrics_bundle(normalized_bundle: NormalizedBundle) -> MetricsBundle:
    return _build_metrics_bundle(normalized_bundle)


def build_metrics(bundle: NormalizedBundle) -> MetricsBundle:
    return _build_metrics_bundle(bundle)


__all__ = ["build_metrics_bundle", "build_metrics"]
