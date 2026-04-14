import tempfile
import unittest
from pathlib import Path

from v3.outputs.daily_artifacts_stage import prepare_daily_output_payload
from v3.outputs.daily_report_stage import run_daily_report_stage
from v3.pipeline.daily_metrics_stage import run_daily_metrics_stage


class TestFinancialKernelPipelineParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_dir = tempfile.TemporaryDirectory()
        out_dir = str(Path(cls._tmp_dir.name) / "out")
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        cls.metrics_ctx = run_daily_metrics_stage(
            {
                "repo_root": "",
                "seller_id": "seller_001",
                "run_date": "2026-04-13",
                "seller_name": "Seller",
                "out_dir": out_dir,
                "token": "",
                "source_mode": "local_reports",
                "cfg": {"tax_rate": 0.06},
                "sales_rows": [
                    {
                        "supplier_oper_name": sale,
                        "nm_id": 101,
                        "quantity": 8,
                        "retail_amount": 7221,
                        "ppvz_sales_commission": 173,
                        "delivery_rub": -492,
                        "storage_fee": -65,
                        "ppvz_for_pay": 4895,
                    }
                ],
                "ads_rows": [],
                "stocks_rows": [],
                "api_orders_rows": [],
                "api_sales_rows": [],
                "api_realization_rows": [],
                "api_stocks_rows": [],
                "supplier_goods_daily": {
                    "found": True,
                    "orders_count": 6,
                    "orders_amount": 5001,
                    "buyouts_count": 8,
                    "buyouts_amount": 4880,
                    "orders_count_confirmed": True,
                    "buyouts_count_confirmed": True,
                    "amounts_confirmed": True,
                },
                "cogs_rows": [{"sku": "101", "cogs": 258.75}],
                "cogs_file_found": True,
                "discovered_files": {},
                "input_debug": {},
                "api_debug": {},
            }
        )
        cls.payload = prepare_daily_output_payload(cls.metrics_ctx)
        try:
            cls.report_ctx = run_daily_report_stage(cls.payload)
        except FileNotFoundError:
            cls.report_ctx = None

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp_dir.cleanup()

    def _require_report(self) -> None:
        if self.report_ctx is None:
            self.skipTest("TTF font for PDF is not available in this environment")

    def test_kernel_output_to_facts_to_report_summary_parity(self) -> None:
        self._require_report()
        financial_kpi = self.metrics_ctx.get("financial_kpi", {})
        facts = self.metrics_ctx.get("facts", {})
        report_fin = self.report_ctx.get("report_meta", {}).get("daily_financial_kpi", {})

        self.assertEqual(
            round(float(financial_kpi.get("gross_revenue", 0.0) or 0.0), 2),
            round(float((facts.get("financial_kpi", {}) if isinstance(facts, dict) else {}).get("gross_revenue", 0.0) or 0.0), 2),
        )
        self.assertEqual(
            round(float(financial_kpi.get("seller_payout", 0.0) or 0.0), 2),
            round(float((facts.get("financial_kpi", {}) if isinstance(facts, dict) else {}).get("seller_payout", 0.0) or 0.0), 2),
        )
        self.assertEqual(
            round(float(financial_kpi.get("gross_revenue", 0.0) or 0.0), 2),
            round(float(report_fin.get("gross_revenue", 0.0) or 0.0), 2),
        )
        self.assertEqual(
            round(float(financial_kpi.get("seller_payout", 0.0) or 0.0), 2),
            round(float(report_fin.get("seller_payout", 0.0) or 0.0), 2),
        )

    def test_gross_revenue_is_not_payout(self) -> None:
        self._require_report()
        financial_kpi = self.metrics_ctx.get("financial_kpi", {})
        report_fin = self.report_ctx.get("report_meta", {}).get("daily_financial_kpi", {})
        self.assertNotEqual(
            round(float(financial_kpi.get("gross_revenue", 0.0) or 0.0), 2),
            round(float(financial_kpi.get("seller_payout", 0.0) or 0.0), 2),
        )
        self.assertNotEqual(
            round(float(report_fin.get("gross_revenue", 0.0) or 0.0), 2),
            round(float(report_fin.get("seller_payout", 0.0) or 0.0), 2),
        )

    def test_storage_preserved_through_pipeline(self) -> None:
        self._require_report()
        financial_kpi = self.metrics_ctx.get("financial_kpi", {})
        facts = self.metrics_ctx.get("facts", {})
        report_fin = self.report_ctx.get("report_meta", {}).get("daily_financial_kpi", {})
        self.assertEqual(round(float(financial_kpi.get("storage", 0.0) or 0.0), 2), 65.0)
        self.assertEqual(
            round(float((facts.get("financial_kpi", {}) if isinstance(facts, dict) else {}).get("storage", 0.0) or 0.0), 2),
            65.0,
        )
        self.assertEqual(round(float(report_fin.get("storage", 0.0) or 0.0), 2), 65.0)

    def test_buyouts_parity_across_kpi_funnel_and_summary(self) -> None:
        self._require_report()
        daily_kpi = self.metrics_ctx.get("daily_kpi", {})
        render_kpi = self.metrics_ctx.get("render_kpi", {})
        report_commerce = self.report_ctx.get("report_meta", {}).get("daily_commerce_kpi", {})
        report_funnel = self.report_ctx.get("visual_payload", {}).get("funnel", {})

        self.assertEqual(int(daily_kpi.get("daily_buyouts_count", 0) or 0), 8)
        self.assertEqual(int(render_kpi.get("buyouts_count", 0) or 0), 8)
        self.assertEqual(int(report_commerce.get("daily_buyouts_count", 0) or 0), 8)
        self.assertEqual(int(float(report_funnel.get("buyouts", 0) or 0)), 8)

    def test_sku_table_uses_kernel_sku_financials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {
                "out_dir": tmp_dir,
                "seller_id": "seller_001",
                "run_date": "2026-04-13",
                "job": {"email_summary": {"key_insights": ["ok"], "recommendations": ["ok"]}},
                "financial_kpi": {
                    "revenue": 1000.0,
                    "seller_payout": 1000.0,
                    "gross_revenue": 1200.0,
                    "wb_realized_revenue": 1200.0,
                    "wb_commission": 100.0,
                    "logistics": 50.0,
                    "storage": 10.0,
                    "tax": 60.0,
                    "cost_price": 500.0,
                    "net_profit": 200.0,
                    "financial_finality_status": "final",
                    "is_partial": False,
                    "components": {
                        "revenue": {"available": True},
                        "seller_payout": {"available": True},
                        "commission": {"available": True},
                        "acquiring": {"available": True},
                        "pvz_service": {"available": True},
                        "logistics": {"available": True},
                        "storage": {"available": True},
                        "deductions": {"available": True},
                        "cost_price": {"available": True},
                        "tax": {"available": True},
                        "ads_spend": {"available": True},
                        "net_profit": {"available": True},
                    },
                },
                "daily_kpi": {
                    "orders_count_confirmed": True,
                    "buyouts_count_confirmed": True,
                    "daily_orders_count": 1,
                    "daily_buyouts_count": 1,
                    "daily_buyouts_amount": 1000.0,
                },
                "render_kpi": {
                    "orders_count": 1,
                    "buyouts_count": 1,
                    "buyouts_amount": 1000.0,
                    "avg_check": 1000.0,
                    "revenue": 1000.0,
                    "net_profit": 200.0,
                    "margin_pct": 20.0,
                },
                "kernel_sku_financials": {
                    101: {"payout": 200.0, "profit": 50.0, "net_revenue": 210.0},
                },
                "sku_metrics": [{"sku": "101", "revenue": 9999.0, "profit": 9999.0}],
            }
            out = run_daily_report_stage(payload)
            sku_rows = out.get("visual_payload", {}).get("sku_profit_rows", [])
            self.assertTrue(isinstance(sku_rows, list) and sku_rows)
            self.assertIn("200", str(sku_rows[0].get("revenue")))
            self.assertIn("50", str(sku_rows[0].get("profit")))

    def test_regression_case_2026_04_13_reference_subset(self) -> None:
        self._require_report()
        financial_kpi = self.metrics_ctx.get("financial_kpi", {})
        report_fin = self.report_ctx.get("report_meta", {}).get("daily_financial_kpi", {})
        report_commerce = self.report_ctx.get("report_meta", {}).get("daily_commerce_kpi", {})

        self.assertEqual(round(float(financial_kpi.get("gross_revenue", 0.0) or 0.0), 2), 7221.0)
        self.assertEqual(round(float(financial_kpi.get("seller_payout", 0.0) or 0.0), 2), 4895.0)
        self.assertEqual(round(float(financial_kpi.get("wb_commission", 0.0) or 0.0), 2), 173.0)
        self.assertEqual(round(float(financial_kpi.get("logistics", 0.0) or 0.0), 2), 492.0)
        self.assertEqual(round(float(financial_kpi.get("storage", 0.0) or 0.0), 2), 65.0)
        self.assertEqual(int(report_commerce.get("daily_buyouts_count", 0) or 0), 8)
        self.assertEqual(round(float(report_commerce.get("daily_buyouts_amount", 0.0) or 0.0), 2), 4880.0)
        self.assertEqual(round(float(report_fin.get("gross_revenue", 0.0) or 0.0), 2), 7221.0)
        self.assertEqual(round(float(report_fin.get("seller_payout", 0.0) or 0.0), 2), 4895.0)


if __name__ == "__main__":
    unittest.main()
