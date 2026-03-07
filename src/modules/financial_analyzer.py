from __future__ import annotations
from typing import Any, Dict
from src.metrics import calc_financial_metrics

def analyze_finance(realization_raw: Any, tax_rate: float = 0.06) -> Dict[str, Any]:
    """Finance metrics wrapper."""
    return calc_financial_metrics(realization_raw, tax_rate=tax_rate)
