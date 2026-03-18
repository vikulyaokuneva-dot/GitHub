"""Summary Assembler skeleton.

Input: MetricsBundle sections and mode context.
Output: section-level placeholders.
Does not perform production KPI calculations in stage 1.
"""

from __future__ import annotations

from typing import Any, Dict


def build(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    _ = payload
    return {"status": "not_implemented", "stage": "skeleton"}
