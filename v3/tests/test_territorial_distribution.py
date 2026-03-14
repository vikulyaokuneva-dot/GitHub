import json

import os

import tempfile

import unittest



from v3.analytics.territorial_distribution import build_territorial_distribution, lookup_distribution_coefficients

from v3.outputs.artifacts_writer import write_daily_metrics_artifacts





class TestTerritorialDistributionEngine(unittest.TestCase):

    def _item(self, payload, sku):

        items = payload.get("items", []) if isinstance(payload, dict) else []

        for row in items:

            if isinstance(row, dict) and str(row.get("sku") or "") == sku:

                return row

        return {}



    def test_coefficient_lookup(self) -> None:

        c0 = lookup_distribution_coefficients(0.0)

        c60 = lookup_distribution_coefficients(60.0)

        c77 = lookup_distribution_coefficients(77.0)

        c100 = lookup_distribution_coefficients(100.0)



        self.assertAlmostEqual(c0.ktr, 2.0, places=6)

        self.assertAlmostEqual(c0.krp, 0.025, places=6)

        self.assertAlmostEqual(c60.ktr, 1.0, places=6)

        self.assertAlmostEqual(c60.krp, 0.0, places=6)

        self.assertAlmostEqual(c77.ktr, 0.9, places=6)

        self.assertAlmostEqual(c77.krp, 0.0, places=6)

        self.assertAlmostEqual(c100.ktr, 0.5, places=6)



    def test_localization_and_state_classification(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [

                    {"sku": "SKU_STRONG", "orders": 10, "local_orders": 8, "revenue": 1000},

                    {"sku": "SKU_WEAK", "orders": 10, "local_orders": 3, "revenue": 1000},

                    {"sku": "SKU_CRIT", "orders": 10, "local_orders": 1, "revenue": 1000},

                ]

            },

            run_date="2026-03-24",

        )



        strong = self._item(payload, "SKU_STRONG")

        weak = self._item(payload, "SKU_WEAK")

        critical = self._item(payload, "SKU_CRIT")



        self.assertEqual(strong.get("distribution_state"), "strong")

        self.assertEqual(weak.get("distribution_state"), "weak")

        self.assertEqual(critical.get("distribution_state"), "critical")



        self.assertEqual(float(strong.get("estimated_irp_penalty_total", 0.0) or 0.0), 0.0)

        self.assertGreater(float(weak.get("estimated_irp_penalty_total", 0.0) or 0.0), 0.0)

        self.assertGreater(float(critical.get("estimated_irp_penalty_total", 0.0) or 0.0), 0.0)



        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}

        self.assertEqual(int(summary.get("skus_below_60_localization", 0) or 0), 2)



    def test_localization_share_from_warehouse_data(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [{"sku": "SKU_WH", "orders": 10, "revenue": 1000}],

                "sales_rows": [

                    {"sku": "SKU_WH", "warehouse": "wh_a", "orders": 6},

                    {"sku": "SKU_WH", "warehouse": "wh_b", "orders": 4},

                ],

            },

            stocks_raw=[{"sku": "SKU_WH", "stock_by_warehouse": {"wh_a": 100}}],

            run_date="2026-03-24",

        )



        item = self._item(payload, "SKU_WH")

        self.assertAlmostEqual(float(item.get("local_orders", 0.0) or 0.0), 6.0, places=6)

        self.assertAlmostEqual(float(item.get("localization_share", 0.0) or 0.0), 60.0, places=6)

        self.assertEqual(item.get("distribution_state"), "strong")





    def test_effective_date_gating_before_2026_03_23(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [

                    {"sku": "SKU_PREVIEW", "orders": 10, "local_orders": 1, "revenue": 1000},

                ]

            },

            run_date="2026-03-22",

        )



        item = self._item(payload, "SKU_PREVIEW")

        self.assertEqual(float(item.get("estimated_irp_penalty_total", 0.0) or 0.0), 0.0)

        self.assertEqual(float(item.get("irp_penalty_per_order", 0.0) or 0.0), 0.0)

        self.assertFalse(bool(item.get("effective_date_applied", False)))



    def test_zero_krp_penalty_when_localization_60_plus(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [{"sku": "SKU_60", "orders": 10, "local_orders": 6, "revenue": 1000}],

            },

            run_date="2026-03-24",

        )

        item = self._item(payload, "SKU_60")

        self.assertAlmostEqual(float(item.get("krp", 0.0) or 0.0), 0.0, places=6)

        self.assertAlmostEqual(float(item.get("estimated_irp_penalty_total", 0.0) or 0.0), 0.0, places=6)



    def test_missing_data_is_safe(self) -> None:

        payload = build_territorial_distribution({}, run_date="2026-03-24")

        self.assertEqual(payload.get("status"), "insufficient_data")

        self.assertEqual(len(payload.get("items", [])), 0)

        warnings = payload.get("warnings", []) if isinstance(payload, dict) else []

        self.assertTrue(any(isinstance(w, dict) and str(w.get("code") or "").startswith("territorial_distribution") for w in warnings))




    def test_missing_local_orders_does_not_force_zero_localization(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [{"sku": "SKU_UNKNOWN", "orders": 12, "revenue": 1000}],

            },

            run_date="2026-03-24",

        )

        item = self._item(payload, "SKU_UNKNOWN")

        self.assertIsNone(item.get("localization_share"))

        self.assertIn(str(item.get("analysis_mode") or ""), {"preview", "disabled"})

        signals = payload.get("signals", []) if isinstance(payload, dict) else []

        self.assertTrue(any(str(s.get("signal_type") or "") == "distribution_insufficient_data" for s in signals if isinstance(s, dict)))



    def test_low_sample_sku_is_preview_low_confidence(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [{"sku": "SKU_LOW", "orders": 1, "revenue": 1000}],

                "sales_rows": [{"sku": "SKU_LOW", "warehouse": "wh_a", "orders": 1}],

            },

            stocks_raw=[{"sku": "SKU_LOW", "stock_by_warehouse": {"wh_a": 10}}],

            run_date="2026-03-24",

        )

        item = self._item(payload, "SKU_LOW")

        self.assertEqual(str(item.get("confidence") or ""), "low")

        self.assertEqual(str(item.get("analysis_mode") or ""), "preview")

        self.assertEqual(str(item.get("recommendation_status") or ""), "watch")



    def test_portfolio_summary_is_suppressed_under_low_coverage(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [

                    {"sku": "A", "orders": 10, "local_orders": 5, "revenue": 1000},

                    {"sku": "B", "orders": 10, "revenue": 1000},

                    {"sku": "C", "orders": 10, "revenue": 1000},

                    {"sku": "D", "orders": 10, "revenue": 1000},

                    {"sku": "E", "orders": 10, "revenue": 1000},

                ]

            },

            run_date="2026-03-24",

        )

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}

        self.assertTrue(bool(summary.get("suppressed_due_to_data_quality", False)))

        self.assertIn(str(summary.get("analysis_mode") or ""), {"preview", "disabled"})

        self.assertLess(float(summary.get("coverage_pct", 0.0) or 0.0), 40.0)



    def test_strong_signal_emits_only_with_sufficient_evidence(self) -> None:

        payload = build_territorial_distribution(

            {

                "sku_metrics": [

                    {"sku": "SKU_CRIT_OK", "orders": 12, "revenue": 1000},

                    {"sku": "SKU_CRIT_UNKNOWN", "orders": 12, "revenue": 1000},

                ],

                "sales_rows": [

                    {"sku": "SKU_CRIT_OK", "warehouse": "wh_a", "orders": 12},

                    {"sku": "SKU_CRIT_UNKNOWN", "warehouse": "wh_a", "orders": 12},

                ],

            },

            stocks_raw=[

                {"sku": "SKU_CRIT_OK", "stock_by_warehouse": {"wh_b": 100}},

            ],

            run_date="2026-03-24",

        )

        signals = [row for row in (payload.get("signals", []) if isinstance(payload, dict) else []) if isinstance(row, dict)]

        crit_ok = [s for s in signals if str(s.get("entity_id") or "") == "SKU_CRIT_OK" and str(s.get("signal_type") or "") == "distribution_critical_sku"]

        crit_unknown = [s for s in signals if str(s.get("entity_id") or "") == "SKU_CRIT_UNKNOWN" and str(s.get("signal_type") or "") == "distribution_critical_sku"]

        unknown_data = [s for s in signals if str(s.get("entity_id") or "") == "SKU_CRIT_UNKNOWN" and str(s.get("signal_type") or "") in {"distribution_insufficient_data", "distribution_low_confidence"}]

        self.assertTrue(bool(crit_ok))

        self.assertFalse(bool(crit_unknown))

        self.assertTrue(bool(unknown_data))

    def test_writer_creates_territorial_artifacts(self) -> None:

        territorial = build_territorial_distribution(

            {

                "sku_metrics": [{"sku": "SKU_OUT", "orders": 5, "local_orders": 2, "revenue": 500}],

            },

            run_date="2026-03-24",

        )



        with tempfile.TemporaryDirectory() as tmp:

            write_daily_metrics_artifacts(

                out_dir=tmp,

                metrics={},

                financial_debug=[],

                abc_rows=[],

                profit_contribution={},

                keyword_monitoring={},

                territorial_distribution=territorial,

            )



            self.assertTrue(os.path.isfile(os.path.join(tmp, "territorial_distribution.json")))

            self.assertTrue(os.path.isfile(os.path.join(tmp, "territorial_distribution_summary.json")))

            self.assertTrue(os.path.isfile(os.path.join(tmp, "territorial_distribution_metrics.json")))



            with open(os.path.join(tmp, "territorial_distribution_summary.json"), "r", encoding="utf-8") as file:

                summary_payload = json.load(file)

            self.assertIn("summary", summary_payload)





if __name__ == "__main__":

    unittest.main()

