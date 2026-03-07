from __future__ import annotations
from typing import Any, Dict, List

def compute_data_confidence(warnings: List[Dict[str, Any]]) -> str:
    """high/medium/low based on warnings."""
    if not warnings:
        return "high"
    codes = {str(w.get("code","")) for w in warnings}
    if "wb_token_missing" in codes or "wb_api_error" in codes:
        return "low"
    return "medium"
