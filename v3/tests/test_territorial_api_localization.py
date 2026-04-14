import unittest

from v3.analytics.territorial_distribution import build_territorial_distribution


class TestTerritorialApiLocalizationReadiness(unittest.TestCase):
    def _item(self, payload, sku):
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for row in items:
            if isinstance(row, dict) and str(row.get("sku") or "") == sku:
                return row
        return {}

    def test_usable_mode_and_recommendations_when_geo_coverage_is_good(self) -> None:
        payload = build_territorial_distribution(
            {
                "sku_metrics": [{"sku": "SKU1", "orders": 20, "revenue": 2000}],
                "sales_rows": [
                    {"sku": "SKU1", "orders": 16, "warehouse": "region_a", "region": "region_a"},
                    {"sku": "SKU1", "orders": 4, "warehouse": "region_b", "region": "region_b"},
                ],
            },
            stocks_raw=[{"sku": "SKU1", "stock_by_warehouse": {"region_b": 100}}],
            run_date="2026-03-24",
        )

        item = self._item(payload, "SKU1")
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertEqual(str(payload.get("analysis_mode") or ""), "full")
        self.assertEqual(str(payload.get("analysis_status") or ""), "usable")
        self.assertEqual(str(payload.get("recommendation_status") or ""), "actionable")
        self.assertTrue(bool(item.get("recommendation_candidates")))
        self.assertEqual(str((item.get("recommendation_candidates")[0] or {}).get("destination_region") or ""), "region a")
        self.assertGreater(float(item.get("non_local_orders_estimate", 0.0) or 0.0), 0.0)
        self.assertGreater(int(summary.get("actionable_recommendation_skus", 0) or 0), 0)

    def test_preview_mode_with_specific_blocked_reasons_on_partial_geo(self) -> None:
        payload = build_territorial_distribution(
            {
                "sku_metrics": [{"sku": "SKU2", "orders": 10, "revenue": 1000}],
                "sales_rows": [{"sku": "SKU2", "orders": 10, "warehouse": "wh_a", "region": "wh_a"}],
            },
            stocks_raw=[],
            run_date="2026-03-24",
        )

        item = self._item(payload, "SKU2")
        self.assertEqual(str(item.get("analysis_mode") or ""), "preview")
        self.assertEqual(str(item.get("analysis_status") or ""), "preview")
        blocked = [str(reason) for reason in list(item.get("blocked_reasons", []))]
        self.assertIn("missing_stock_geography", blocked)
        self.assertIn("localization_not_computable", blocked)
        self.assertEqual(str(item.get("recommendation_status") or ""), "watch")

    def test_blocked_by_data_with_detailed_reasons_on_no_geo(self) -> None:
        payload = build_territorial_distribution(
            {
                "sku_metrics": [{"sku": "SKU3", "orders": 8, "revenue": 800}],
                "sales_rows": [{"sku": "SKU3", "orders": 8}],
            },
            stocks_raw=[],
            run_date="2026-03-24",
        )

        item = self._item(payload, "SKU3")
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertEqual(str(item.get("analysis_mode") or ""), "disabled")
        self.assertEqual(str(item.get("analysis_status") or ""), "blocked_by_data")
        blocked = [str(reason) for reason in list(item.get("blocked_reasons", []))]
        self.assertIn("missing_demand_geography", blocked)
        self.assertIn("missing_stock_geography", blocked)
        self.assertIn("localization_not_computable", blocked)
        self.assertIn("missing_demand_geography", [str(reason) for reason in list(summary.get("blocked_reasons", []))])
        self.assertEqual(str(payload.get("analysis_status") or ""), "blocked_by_data")
        self.assertEqual(str(payload.get("recommendation_status") or ""), "blocked_by_data")


if __name__ == "__main__":
    unittest.main()
