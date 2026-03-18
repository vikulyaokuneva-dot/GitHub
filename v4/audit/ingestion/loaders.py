"""Loaders skeleton.

Input: mode-specific payload.
Output: placeholder structure for next implementation stage.
Does not execute production business logic.
"""

from __future__ import annotations

from typing import Any, Dict


def run(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    _ = payload
    return {"status": "not_implemented", "stage": "skeleton"}
