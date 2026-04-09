from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.localization_loss import (
    estimate_loss_per_order,
    estimate_total_localization_loss,
    estimate_total_localization_loss_for_sku,
)


def test_full_mode_with_rub_result():
    result = estimate_total_localization_loss(
        sku_rows=[{"sku": 111, "orders": 10, "item_price": 1000.0, "volume_liters": 1.0, "localization_share_pct": 30.0}],
        localization_share_pct=30.0,
        non_local_orders_share=0.7,
        default_volume_liters=1.0,
        default_item_price=1000.0,
        warehouse_coef=1.0,
        revenue_total=10000.0,
    )

    assert result["estimation_mode"] == "full_rub"
    assert result["total_estimated_loss_rub"] == 375.0
    assert result["loss_share_of_revenue"] == 0.0375


def test_partial_mode_with_fallback_avg_price():
    result = estimate_total_localization_loss(
        sku_rows=[{"sku": 222, "orders": 10, "volume_liters": 1.0, "localization_share_pct": 30.0}],
        localization_share_pct=30.0,
        non_local_orders_share=0.7,
        default_volume_liters=1.0,
        default_item_price=1000.0,
        warehouse_coef=1.0,
        revenue_total=10000.0,
    )

    assert result["estimation_mode"] == "partial_rub"
    assert (result["total_estimated_loss_rub"] or 0) > 0


def test_score_only_mode():
    result = estimate_total_localization_loss(
        sku_rows=[{"sku": 333, "orders": 10, "localization_share_pct": 30.0}],
        localization_share_pct=30.0,
        non_local_orders_share=0.7,
        default_volume_liters=None,
        default_item_price=None,
        warehouse_coef=1.0,
        revenue_total=10000.0,
    )

    assert result["estimation_mode"] == "score_only"
    assert result["total_estimated_loss_rub"] is None
    assert len(result["top_loss_sku"]) == 1
    assert result["top_loss_sku"][0]["risk_level"] in {"medium", "high", "critical", "unknown"}


def test_zero_orders():
    result = estimate_total_localization_loss(
        sku_rows=[{"sku": 444, "orders": 0, "item_price": 1000.0, "volume_liters": 1.0, "localization_share_pct": 30.0}],
        localization_share_pct=30.0,
        non_local_orders_share=0.7,
        default_volume_liters=1.0,
        default_item_price=1000.0,
        warehouse_coef=1.0,
        revenue_total=10000.0,
    )

    assert result["status"] == "insufficient_data"
    assert result["estimation_mode"] == "insufficient_data"
    assert result["total_estimated_loss_rub"] is None


def test_all_local_orders():
    result = estimate_total_localization_loss(
        sku_rows=[{"sku": 555, "orders": 10, "item_price": 1000.0, "volume_liters": 1.0, "localization_share_pct": 100.0}],
        localization_share_pct=100.0,
        non_local_orders_share=0.0,
        default_volume_liters=1.0,
        default_item_price=1000.0,
        warehouse_coef=1.0,
        revenue_total=10000.0,
    )

    assert result["estimation_mode"] == "full_rub"
    assert result["non_local_orders_share"] == 0.0
    assert result["total_estimated_loss_rub"] == 0.0


def test_mostly_non_local_orders():
    result = estimate_total_localization_loss(
        sku_rows=[{"sku": 666, "orders": 10, "item_price": 1000.0, "volume_liters": 1.0, "localization_share_pct": 20.0}],
        localization_share_pct=20.0,
        non_local_orders_share=0.8,
        default_volume_liters=1.0,
        default_item_price=1000.0,
        warehouse_coef=1.0,
        revenue_total=10000.0,
    )

    assert result["non_local_orders_share"] == 0.8
    assert any("распределения остатков" in (x.get("action") or "").lower() for x in (result.get("recommendations") or []))


def test_loss_per_order_api():
    row = estimate_loss_per_order(
        volume_liters=1.0,
        item_price=1000.0,
        warehouse_coef=1.0,
        localization_share_pct=30.0,
    )
    assert row["loss_per_order_rub"] == 37.5


def test_estimate_total_loss_for_sku_score_only():
    row = estimate_total_localization_loss_for_sku(
        sku=777,
        orders_count=7,
        localization_share_pct=30.0,
        volume_liters=None,
        item_price=None,
        avg_price_fallback=None,
    )
    assert row["mode"] == "score_only"
    assert row["risk_level"] in {"medium", "high", "critical", "unknown"}


def test_loss_per_order_respects_forced_il_irp_from_config() -> None:
    row = estimate_loss_per_order(
        volume_liters=1.0,
        item_price=1000.0,
        warehouse_coef=1.0,
        localization_share_pct=None,
        forced_localization_index=1.12,
        forced_sales_distribution_index_pct=0.99,
    )
    assert row["localization_index"] == 1.12
    assert row["sales_distribution_index_pct"] == 0.99
    assert row["loss_per_order_rub"] == 13.74
