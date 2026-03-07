from __future__ import annotations
from typing import Any, Dict
from src.metrics import calc_stock_forecast

def analyze_stocks(stocks_raw: Any, sales_last_30d: int = 0) -> Dict[str, Any]:
    """Stock forecast wrapper."""
    return calc_stock_forecast(stocks_raw, sales_last_30d=sales_last_30d)
