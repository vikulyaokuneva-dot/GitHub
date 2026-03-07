from __future__ import annotations
from typing import Any, Dict
from src.metrics import calc_ads_metrics

def analyze_ads(ads_raw: Any) -> Dict[str, Any]:
    """Back-compat wrapper around calc_ads_metrics."""
    return calc_ads_metrics(ads_raw)
