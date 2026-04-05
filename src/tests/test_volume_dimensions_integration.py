from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_sku_dimensions, _estimate_volume_liters_from_sku_dimensions
from audit.audit_loader import _extract_volume_liters_from_stocks_row


def test_extract_volume_liters_from_stocks_row_direct():
    volume, source = _extract_volume_liters_from_stocks_row({"Объем, л": "0,45"})
    assert volume == 0.45
    assert source == "stocks"


def test_extract_volume_liters_from_stocks_row_by_dimensions():
    volume, source = _extract_volume_liters_from_stocks_row(
        {"Длина, см": 20, "Ширина, см": 10, "Высота, см": 5}
    )
    assert volume == 1.0
    assert source == "calculated"


def test_build_sku_dimensions_and_coverage():
    sku_dimensions, coverage = _build_sku_dimensions(
        [
            {"nmId": 1, "volume_liters": 0.75, "volume_source": "stocks"},
            {"nmId": 2, "volume_liters": None, "volume_source": "missing"},
            {"nmId": 3, "volume_liters": 1.2, "volume_source": "calculated"},
            {"nmId": 3, "volume_liters": 1.0, "volume_source": "calculated"},
        ]
    )

    assert sku_dimensions[1]["volume_liters"] == 0.75
    assert sku_dimensions[1]["source"] == "stocks"
    assert sku_dimensions[2]["volume_liters"] is None
    assert sku_dimensions[2]["source"] == "missing"
    assert sku_dimensions[3]["volume_liters"] == 1.1
    assert sku_dimensions[3]["source"] == "calculated"
    assert coverage == {"total_sku": 3, "with_volume": 2, "calculated": 1, "missing": 1}


def test_estimate_volume_liters_from_sku_dimensions_median():
    volume, source = _estimate_volume_liters_from_sku_dimensions(
        {
            1: {"volume_liters": 0.5, "source": "stocks"},
            2: {"volume_liters": 1.5, "source": "stocks"},
            3: {"volume_liters": None, "source": "missing"},
        }
    )
    assert volume == 1.0
    assert source == "stocks"
