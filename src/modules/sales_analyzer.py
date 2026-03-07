from __future__ import annotations
from typing import Any, Dict
from src.metrics import calc_funnel_metrics

def analyze_sales(funnel_raw: Any) -> Dict[str, Any]:
    """Sales funnel metrics wrapper."""
    return calc_funnel_metrics(funnel_raw)
