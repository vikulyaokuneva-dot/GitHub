import unittest

import tempfile

from v3.analytics.profit_contribution import build_profit_contribution
from v3.pipeline.daily_metrics_stage import run_daily_metrics_stage


class TestProfitContribution(unittest.TestCase):
    def _item_by_sku(self, payload, sku):
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for row in items:
            if isinstance(row, dict) and str(row.get("sku") or "") == sku:
                return row
        return {}

    def test_contract_groups_and_summary(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "A", "revenue": 5000, "profit": 800},
                    {"sku": "B", "revenue": 3000, "profit": 150},
                    {"sku": "C", "revenue": 1000, "profit": 50},
                    {"sku": "D", "revenue": 700, "profit": -20},
                    {"sku": "E", "revenue": 400, "profit": None},
                ]
            }
        )

        self.assertIn(payload.get("status"), {"ok", "partial", "insufficient_data"})
        self.assertIsInstance(payload.get("warnings", []), list)
        self.assertIsInstance(payload.get("items", []), list)

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertEqual(int(summary.get("sku_count", 0)), 5)
        self.assertEqual(int(summary.get("profit_sku_count", 0)), 3)
        self.assertEqual(int(summary.get("loss_sku_count", 0)), 1)
        self.assertEqual(float(summary.get("total_revenue", 0.0)), 10100.0)
        self.assertIn(summary.get("profit_concentration"), {"high", "medium", "low", "insufficient_data"})
        self.assertAlmostEqual(float(summary.get("top_20_profit_share", 0.0) or 0.0), 0.8, places=6)
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        self.assertEqual(float(meta.get("total_revenue", 0.0)), 10100.0)

        a = self._item_by_sku(payload, "A")
        b = self._item_by_sku(payload, "B")
        d = self._item_by_sku(payload, "D")
        e = self._item_by_sku(payload, "E")

        self.assertEqual(a.get("profit_group"), "P1")
        self.assertEqual(b.get("profit_group"), "P2")
        self.assertEqual(d.get("profit_group"), "P4")
        self.assertEqual(e.get("status"), "insufficient_data")
        self.assertIn("profit_missing", e.get("warnings", []))

        # Backward compatibility for current report/facts layer.
        for key in ("p1", "p2", "p3", "p4", "top_profit_skus", "meta"):
            self.assertIn(key, payload)

    def test_non_positive_total_profit_marks_share_as_unavailable(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "P", "profit": 10},
                    {"sku": "L", "profit": -20},
                ]
            }
        )
        item_p = self._item_by_sku(payload, "P")
        self.assertIsNone(item_p.get("profit_share"))
        self.assertIn("total_profit_non_positive", item_p.get("warnings", []))

    def test_missing_input_is_safe(self) -> None:
        payload = build_profit_contribution({})
        self.assertEqual(payload.get("status"), "insufficient_data")
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertEqual(int(summary.get("sku_count", 0)), 0)

    def test_total_revenue_is_none_when_revenue_is_missing(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "P", "profit": 10},
                    {"sku": "L", "profit": -2, "revenue": None},
                ]
            }
        )

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        self.assertIsNone(summary.get("total_revenue"))
        self.assertIsNone(meta.get("total_revenue"))

    def test_total_revenue_accepts_sku_fact_table_revenue_fields(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "ORDER", "orders_revenue": 1760.0, "profit": None},
                    {"sku": "REALIZED", "realized_revenue": 554.0, "profit": None},
                ]
            }
        )

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        self.assertEqual(float(summary.get("total_revenue", 0.0)), 2314.0)
        self.assertEqual(float(meta.get("total_revenue", 0.0)), 2314.0)
        self.assertEqual(len(payload.get("sku_pnl", [])), 2)

    def test_daily_metrics_stage_uses_sku_fact_table_for_profit_when_sku_metrics_missing(self) -> None:
        with tempfile.TemporaryDirectory() as out_dir:
            ctx = run_daily_metrics_stage(
                {
                    "repo_root": "",
                    "seller_id": "seller_sku_fact",
                    "run_date": "2026-04-29",
                    "seller_name": "Seller SKU Fact",
                    "out_dir": out_dir,
                    "token": "token",
                    "source_mode": "wb_api",
                    "cfg": {"tax_rate": 0.06},
                    "sales_rows": [],
                    "ads_rows": [],
                    "stocks_rows": [],
                    "api_orders_rows": [],
                    "api_sales_rows": [],
                    "api_realization_rows": [],
                    "api_stocks_rows": [],
                    "supplier_goods_daily": {},
                    "discovered_files": {},
                    "input_debug": {},
                    "api_debug": {},
                    "orders_rows": [
                        {
                            "date": "2026-04-29",
                            "nm_id": "1001",
                            "supplierArticle": "SKU-1001",
                            "quantity": 2,
                            "priceWithDisc": 1760.0,
                        }
                    ],
                }
            )

        profit = ctx.get("profit_contribution", {})
        summary = profit.get("summary", {}) if isinstance(profit, dict) else {}
        diagnostics = ctx.get("metrics", {}).get("diagnostics", {}) if isinstance(ctx.get("metrics"), dict) else {}
        sku_fact_diag = diagnostics.get("sku_fact_table", {}) if isinstance(diagnostics, dict) else {}
        warnings_collector = ctx.get("warnings_collector")
        warning_codes = {
            item.get("code")
            for item in warnings_collector.export_warnings()
            if isinstance(item, dict)
        }

        self.assertEqual(profit.get("source"), "sku_fact_table")
        self.assertEqual(int(profit.get("sku_fact_table_rows", 0)), 1)
        self.assertEqual(float(summary.get("total_revenue", 0.0)), 1760.0)
        self.assertEqual(len(profit.get("items", [])), 1)
        self.assertEqual(len(profit.get("sku_pnl", [])), 1)
        self.assertEqual(int(sku_fact_diag.get("sku_fact_table_rows", 0)), 1)
        self.assertTrue(bool(sku_fact_diag.get("sku_fact_table_source_flags", {}).get("orders")))
        self.assertIn("sku_fact_table_used_for_profit_contribution", warning_codes)
        self.assertNotIn("sku_metrics_missing", set(profit.get("warnings", [])))
        self.assertEqual(ctx.get("sku_metrics"), [])
        self.assertEqual(ctx.get("abc_rows"), [])

    def test_daily_metrics_stage_keeps_sku_metrics_missing_when_fact_rows_empty(self) -> None:
        with tempfile.TemporaryDirectory() as out_dir:
            ctx = run_daily_metrics_stage(
                {
                    "repo_root": "",
                    "seller_id": "seller_no_sku_fact",
                    "run_date": "2026-04-29",
                    "seller_name": "Seller No SKU Fact",
                    "out_dir": out_dir,
                    "token": "token",
                    "source_mode": "wb_api",
                    "cfg": {"tax_rate": 0.06},
                    "sales_rows": [],
                    "ads_rows": [],
                    "stocks_rows": [],
                    "api_orders_rows": [],
                    "api_sales_rows": [],
                    "api_realization_rows": [],
                    "api_stocks_rows": [],
                    "supplier_goods_daily": {},
                    "discovered_files": {},
                    "input_debug": {},
                    "api_debug": {},
                }
            )

        profit = ctx.get("profit_contribution", {})
        summary = profit.get("summary", {}) if isinstance(profit, dict) else {}
        diagnostics = ctx.get("metrics", {}).get("diagnostics", {}) if isinstance(ctx.get("metrics"), dict) else {}
        sku_fact_diag = diagnostics.get("sku_fact_table", {}) if isinstance(diagnostics, dict) else {}

        self.assertNotEqual(profit.get("source"), "sku_fact_table")
        self.assertEqual(profit.get("status"), "insufficient_data")
        self.assertIn("sku_metrics_missing", profit.get("warnings", []))
        self.assertEqual(int(summary.get("sku_count", 0)), 0)
        self.assertEqual(int(sku_fact_diag.get("sku_fact_table_rows", -1)), 0)


if __name__ == "__main__":
    unittest.main()
