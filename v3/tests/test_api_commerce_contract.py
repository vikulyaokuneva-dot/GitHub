import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from v3.analytics.sales_funnel import build_sales_funnel_metrics
from v3.metrics.engine import build_metrics_from_normalized
from v3.normalization.normalizers import normalize_raw_bundle
from v3.pipeline.daily_input_stage import _resolve_funnel_contour_source
from v3.pipeline.daily_metrics_stage import run_daily_metrics_stage
from v3.raw.models import build_raw_bundle


def _api_orders_fixture() -> List[Dict[str, Any]]:
    return [
        {
            "date": "2026-04-14T10:00:00",
            "nmId": 1001,
            "supplierArticle": "SKU-1001",
            "srid": "order-1",
            "quantity": 2,
            "totalPrice": 2000.0,
            "warehouseName": "Moscow WH",
            "regionName": "Moscow",
            "destinationRegion": "Moscow",
        }
    ]


def _api_sales_fixture() -> List[Dict[str, Any]]:
    return [
        {
            "date": "2026-04-14T13:00:00",
            "nmId": 1001,
            "supplierArticle": "SKU-1001",
            "srid": "sale-1",
            "quantity": 1,
            "forPay": 950.0,
            "warehouseName": "Moscow WH",
            "regionName": "Moscow",
        }
    ]


class TestApiCommerceContract(unittest.TestCase):
    def test_funnel_source_is_api_when_lower_funnel_rows_exist(self) -> None:
        self.assertEqual(
            _resolve_funnel_contour_source(
                local_funnel_found=False,
                api_ads_rows=[],
                api_orders_rows=[{"order_id": "1"}],
                api_sales_rows=[],
            ),
            "api",
        )
        self.assertEqual(
            _resolve_funnel_contour_source(
                local_funnel_found=False,
                api_ads_rows=[],
                api_orders_rows=[],
                api_sales_rows=[],
            ),
            "missing",
        )

    def test_builds_funnel_and_orders_contracts_from_api_rows(self) -> None:
        raw_bundle = build_raw_bundle(
            source_mode="wb_api",
            sales_rows=[],
            ads_rows=[],
            stocks_rows=[],
            api_orders_rows=_api_orders_fixture(),
            api_sales_rows=_api_sales_fixture(),
            api_realization_rows=[],
            api_stocks_rows=[],
            supplier_goods_daily={},
            discovered_files={},
            input_debug={},
            api_debug={},
        )
        metrics = build_metrics_from_normalized(normalize_raw_bundle(raw_bundle))

        funnel_rows = metrics.get("funnel_rows_from_api", [])
        self.assertTrue(isinstance(funnel_rows, list) and len(funnel_rows) == 1)
        self.assertAlmostEqual(float(funnel_rows[0].get("orders_count", 0.0) or 0.0), 2.0, places=6)
        self.assertAlmostEqual(float(funnel_rows[0].get("buyouts_count", 0.0) or 0.0), 1.0, places=6)
        self.assertTrue(bool(funnel_rows[0].get("lower_funnel_available", False)))
        self.assertTrue(bool(funnel_rows[0].get("upper_funnel_unavailable_from_api", False)))

        orders_rows = metrics.get("orders_rows_from_api", [])
        self.assertTrue(isinstance(orders_rows, list) and len(orders_rows) == 1)
        self.assertEqual(str(orders_rows[0].get("region") or ""), "Moscow")
        self.assertTrue(bool(orders_rows[0].get("demand_geography_available", False)))

        diagnostics = metrics.get("diagnostics", {})
        api_contract = diagnostics.get("api_funnel_contract", {}) if isinstance(diagnostics, dict) else {}
        self.assertEqual(str(api_contract.get("source") or ""), "api.orders_sales")
        self.assertTrue(bool(api_contract.get("lower_funnel_available", False)))
        self.assertFalse(bool(api_contract.get("upper_funnel_available", True)))

    def test_sku_funnel_uses_api_lower_funnel_when_views_exist(self) -> None:
        raw_bundle = build_raw_bundle(
            source_mode="wb_api",
            sales_rows=[],
            ads_rows=[
                {
                    "date": "2026-04-14",
                    "sku": "1001",
                    "nm_id": "1001",
                    "impressions": 120,
                    "ads_spend": 30.0,
                    "orders": 0,
                    "revenue": 0.0,
                }
            ],
            stocks_rows=[],
            api_orders_rows=_api_orders_fixture(),
            api_sales_rows=_api_sales_fixture(),
            api_realization_rows=[],
            api_stocks_rows=[],
            supplier_goods_daily={},
            discovered_files={},
            input_debug={},
            api_debug={},
        )
        metrics = build_metrics_from_normalized(normalize_raw_bundle(raw_bundle))
        funnel_diag = build_sales_funnel_metrics(metrics, run_date="2026-04-14")
        items = funnel_diag.get("items", []) if isinstance(funnel_diag, dict) else []
        row = next((item for item in items if str(item.get("sku") or "") == "1001"), {})
        self.assertNotEqual(str(row.get("issue_type") or ""), "insufficient_data")

    def test_geo_diagnostics_are_honest_when_geo_fields_are_missing(self) -> None:
        raw_bundle = build_raw_bundle(
            source_mode="wb_api",
            sales_rows=[],
            ads_rows=[],
            stocks_rows=[],
            api_orders_rows=[
                {
                    "date": "2026-04-14T10:00:00",
                    "nmId": 1001,
                    "quantity": 1,
                    "totalPrice": 1000.0,
                }
            ],
            api_sales_rows=[],
            api_realization_rows=[],
            api_stocks_rows=[],
            supplier_goods_daily={},
            discovered_files={},
            input_debug={},
            api_debug={},
        )
        metrics = build_metrics_from_normalized(normalize_raw_bundle(raw_bundle))
        diagnostics = metrics.get("diagnostics", {})
        api_contract = diagnostics.get("api_funnel_contract", {}) if isinstance(diagnostics, dict) else {}
        geo = api_contract.get("geo_completeness", {}) if isinstance(api_contract, dict) else {}
        self.assertIn("region", list(api_contract.get("geo_fields_missing", [])))
        self.assertIn("warehouse", list(api_contract.get("geo_fields_missing", [])))
        self.assertEqual(float(geo.get("demand_geography_coverage_pct", 0.0) or 0.0), 0.0)

    def test_daily_metrics_stage_uses_orders_contract_for_territorial_demand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = str(Path(tmp_dir) / "out")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ctx = run_daily_metrics_stage(
                {
                    "repo_root": "",
                    "seller_id": "seller_api_contract",
                    "run_date": "2026-04-14",
                    "seller_name": "Seller API",
                    "out_dir": out_dir,
                    "token": "token",
                    "source_mode": "wb_api",
                    "cfg": {
                        "tax_rate": 0.06,
                        "territorial_distribution": {
                            "min_portfolio_coverage_pct": 0.0,
                            "min_demand_coverage_pct": 0.0,
                            "min_stock_coverage_pct": 0.0,
                            "max_unknown_share_pct": 100.0,
                        },
                    },
                    "sales_rows": [],
                    "ads_rows": [],
                    "stocks_rows": [{"sku": "1001", "nm_id": "1001", "stock": 10, "warehouse": "Moscow WH"}],
                    "api_orders_rows": _api_orders_fixture(),
                    "api_sales_rows": _api_sales_fixture(),
                    "api_realization_rows": [],
                    "api_stocks_rows": [{"sku": "1001", "nm_id": "1001", "stock": 10, "warehouse": "Moscow WH"}],
                    "supplier_goods_daily": {},
                    "discovered_files": {},
                    "input_debug": {},
                    "api_debug": {"orders_rows": 1, "sales_rows": 1, "realization_rows": 0, "financial_rows": 0},
                }
            )

        metrics = ctx.get("metrics", {})
        diagnostics = metrics.get("diagnostics", {}) if isinstance(metrics, dict) else {}
        api_contract = diagnostics.get("api_funnel_contract", {}) if isinstance(diagnostics, dict) else {}
        territorial_summary = ctx.get("territorial_summary", {})
        daily_kpi = ctx.get("daily_kpi", {})
        commerce_kpi = metrics.get("commerce_kpi", {}) if isinstance(metrics, dict) else {}

        self.assertEqual(str(api_contract.get("source") or ""), "api.orders_sales")
        self.assertGreater(float(territorial_summary.get("demand_coverage_pct", 0.0) or 0.0), 0.0)
        self.assertGreater(int(daily_kpi.get("daily_orders_count", 0) or 0), 0)
        self.assertGreater(int(commerce_kpi.get("daily_buyouts_count", 0) or 0), 0)


if __name__ == "__main__":
    unittest.main()
