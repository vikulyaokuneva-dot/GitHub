"""Shadow-mode exports."""

from .comparator import compare_results
from .contracts import ShadowComparison, ShadowDifference, ShadowRunDiagnostics
from .runner import run_shadow_daily

__all__ = [
    "run_shadow_daily",
    "compare_results",
    "ShadowComparison",
    "ShadowDifference",
    "ShadowRunDiagnostics",
]

