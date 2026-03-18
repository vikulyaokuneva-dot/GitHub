"""Input Stage skeleton.

Input: stage context payload.
Output: stage context payload.
Does not execute production logic in stage 1.
"""

from __future__ import annotations

from typing import Any, Dict


def run(context: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(context or {})
    out.setdefault("stage_trace", []).append("input_stage")
    out["status"] = "not_implemented"
    return out
