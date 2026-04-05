from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.logistics_model import compute_wb_logistics_estimate, localization_indices_by_share


def test_compute_wb_logistics_estimate_volume_below_one_liter():
    result = compute_wb_logistics_estimate(
        volume_liters=0.5,
        item_price=1000.0,
        warehouse_coef=1.2,
        localization_share_pct=95.0,
        supply_type="box",
    )

    assert result["status"] == "complete"
    assert result["tariff_per_liter"] == 29.0
    assert result["localization_index"] == 0.5
    assert result["sales_distribution_index_pct"] == 0.0
    assert result["base_logistics"] == 8.7
    assert result["estimated_delivery_cost"] == 8.7
    assert result["estimated_reverse_logistics"] == 46.0
    assert result["estimated_storage_daily"] == 0.096


def test_compute_wb_logistics_estimate_volume_above_one_liter():
    result = compute_wb_logistics_estimate(
        volume_liters=2.5,
        item_price=1000.0,
        warehouse_coef=1.5,
        localization_share_pct=30.0,
        supply_type="box",
    )

    assert result["status"] == "complete"
    assert result["localization_index"] == 1.5
    assert result["sales_distribution_index_pct"] == 2.15
    assert result["base_logistics"] == 150.75
    assert result["estimated_delivery_cost"] == 172.25
    assert result["estimated_reverse_logistics"] == 67.0
    assert result["estimated_storage_daily"] == 0.3


def test_localization_indices_mapping_for_95_to_100():
    il, irp = localization_indices_by_share(99.9)
    assert il == 0.5
    assert irp == 0.0


def test_localization_indices_mapping_for_30_to_34_99():
    il, irp = localization_indices_by_share(34.5)
    assert il == 1.5
    assert irp == 2.15


def test_localization_indices_mapping_for_0_to_4_99():
    il, irp = localization_indices_by_share(4.0)
    assert il == 2.0
    assert irp == 2.5


def test_compute_wb_logistics_estimate_missing_price():
    result = compute_wb_logistics_estimate(
        volume_liters=2.0,
        item_price=None,
        warehouse_coef=1.0,
        localization_share_pct=30.0,
        supply_type="box",
    )

    assert result["status"] == "partial"
    assert "item_price" in result["missing_inputs"]
    assert result["base_logistics"] == 90.0
    assert result["estimated_delivery_cost"] is None


def test_compute_wb_logistics_estimate_missing_volume():
    result = compute_wb_logistics_estimate(
        volume_liters=None,
        item_price=500.0,
        warehouse_coef=1.0,
        localization_share_pct=95.0,
        supply_type="box",
    )

    assert result["status"] == "missing_inputs"
    assert "volume_liters" in result["missing_inputs"]
    assert result["base_logistics"] is None
    assert result["estimated_delivery_cost"] is None
    assert result["estimated_reverse_logistics"] is None
    assert result["estimated_storage_daily"] is None
