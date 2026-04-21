from __future__ import annotations

from typing import Any, Dict


def build_snapshot(
    *,
    seller_id: str,
    run_date: str,
    operational_date: str,
    timezone_name: str,
    reconcile_result: Dict[str, Any],
) -> Dict[str, Any]:
    orders = reconcile_result.get("orders", {})
    sales = reconcile_result.get("sales", {})
    financial = reconcile_result.get("financial", {})
    stock = reconcile_result.get("stock", {})

    return {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": operational_date,
        "timezone": timezone_name,
        "source_mode": "wb_api_core_v1",
        "daily": {
            "orders_count": orders.get("count"),
            "orders_amount": orders.get("amount"),
            "orders_source": orders.get("source"),
            "orders_available": bool(orders.get("available", False)),
            "buyouts_count": sales.get("count"),
            "buyouts_amount": sales.get("amount"),
            "buyouts_source": sales.get("source"),
            "buyouts_available": bool(sales.get("available", False)),
        },
        "financial": {
            "source": financial.get("source"),
            "available": bool(financial.get("available", False)),
            "target_date": financial.get("target_date"),
            "actual_date": financial.get("actual_date"),
            "date_aligned": financial.get("date_aligned"),
            "gross_revenue": financial.get("gross_revenue"),
            "seller_payout": financial.get("seller_payout"),
            "wb_commission": financial.get("wb_commission"),
            "logistics": financial.get("logistics"),
            "storage": financial.get("storage"),
            "penalties": financial.get("penalties"),
            "deductions": financial.get("deductions"),
            "tax": financial.get("tax"),
            "net_profit": financial.get("net_profit"),
            "margin_pct": financial.get("margin_pct"),
            "finality": financial.get("finality"),
        },
        "stock": {
            "total_units": stock.get("total_units"),
            "source": stock.get("source"),
            "available": bool(stock.get("available", False)),
        },
    }
