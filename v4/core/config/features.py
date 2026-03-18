"""Feature toggles skeleton.

Input: static feature defaults.
Output: feature flag object.
Does not evaluate business logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlags:
    enable_email: bool = True
    enable_pdf: bool = True
    enable_ai_decisions: bool = True
