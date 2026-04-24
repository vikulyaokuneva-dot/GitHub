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
    cabinet_commerce = reconcile_result.get("cabinet_commerce_daily", {})
    funnel = reconcile_result.get("funnel_daily", {})
    finance_final = reconcile_result.get("finance_final_daily", {})
    live_operational = reconcile_result.get("live_operational", {})
    live_orders = live_operational.get("orders", {}) if isinstance(live_operational, dict) else {}
    live_sales = live_operational.get("sales", {}) if isinstance(live_operational, dict) else {}
    live_stocks = live_operational.get("stocks", {}) if isinstance(live_operational, dict) else {}

    return {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": operational_date,
        "timezone": timezone_name,
        "source_mode": "wb_api_core_v2",
        "cabinet_commerce_daily": {
            "source": cabinet_commerce.get("source"),
            "available": bool(cabinet_commerce.get("available", False)),
            "target_date": cabinet_commerce.get("target_date"),
            "orders_count": cabinet_commerce.get("orders_count"),
            "orders_amount": cabinet_commerce.get("orders_amount"),
            "buyouts_count": cabinet_commerce.get("buyouts_count"),
            "buyouts_amount": cabinet_commerce.get("buyouts_amount"),
        },
        "funnel_daily": {
            "source": funnel.get("source"),
            "owner_block": funnel.get("owner_block"),
            "available": bool(funnel.get("available", False)),
            "target_date": funnel.get("target_date"),
            "open_count": funnel.get("open_count"),
            "cart_count": funnel.get("cart_count"),
            "orders_count": funnel.get("orders_count"),
            "orders_amount": funnel.get("orders_amount"),
            "buyouts_count": funnel.get("buyouts_count"),
            "buyouts_amount": funnel.get("buyouts_amount"),
            "open_to_cart_rate": funnel.get("open_to_cart_rate"),
            "cart_to_order_rate": funnel.get("cart_to_order_rate"),
            "order_to_buyout_rate": funnel.get("order_to_buyout_rate"),
            "upper_funnel_status": funnel.get("upper_funnel_status"),
            "lower_funnel_status": funnel.get("lower_funnel_status"),
            "status": funnel.get("status"),
        },
        "finance_final_daily": {
            "source": finance_final.get("source"),
            "available": bool(finance_final.get("available", False)),
            "target_date": finance_final.get("target_date"),
            "actual_date": finance_final.get("actual_date"),
            "date_aligned": finance_final.get("date_aligned"),
            "gross_revenue": finance_final.get("gross_revenue"),
            "seller_payout": finance_final.get("seller_payout"),
            "wb_commission": finance_final.get("wb_commission"),
            "logistics": finance_final.get("logistics"),
            "storage": finance_final.get("storage"),
            "penalties": finance_final.get("penalties"),
            "deductions": finance_final.get("deductions"),
            "acquiring": finance_final.get("acquiring"),
            "tax": finance_final.get("tax"),
        },
        "live_operational": {
            "orders": {
                "source": live_orders.get("source"),
                "available": bool(live_orders.get("available", False)),
                "target_date": live_orders.get("target_date"),
                "count": live_orders.get("count"),
                "amount": live_orders.get("amount"),
            },
            "sales": {
                "source": live_sales.get("source"),
                "available": bool(live_sales.get("available", False)),
                "target_date": live_sales.get("target_date"),
                "count": live_sales.get("count"),
                "amount": live_sales.get("amount"),
            },
            "stocks": {
                "source": live_stocks.get("source"),
                "available": bool(live_stocks.get("available", False)),
                "snapshot_kind": live_stocks.get("snapshot_kind"),
                "operational_date_reference": live_stocks.get("operational_date_reference"),
                "snapshot_date": live_stocks.get("snapshot_date"),
                "total_units": live_stocks.get("total_units"),
            },
        },
    }
