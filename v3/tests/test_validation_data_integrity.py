import unittest

from v3.validation import (
    evaluate_financial_integrity,
    evaluate_sku_attribution,
    normalize_sku,
    resolve_row_sku,
)


class TestSkuNormalization(unittest.TestCase):
    def test_normalize_sku_consistency(self) -> None:
        self.assertEqual(normalize_sku(" 123 "), "123")
        self.assertEqual(normalize_sku(123), "123")
        self.assertEqual(normalize_sku("123.0"), "123")
        self.assertEqual(normalize_sku("WB-001"), "WB-001")
        self.assertIsNone(normalize_sku("0"))
        self.assertIsNone(normalize_sku("bad sku!"))

    def test_resolve_row_sku_prefers_primary_field(self) -> None:
        row = {
            "nmId": "777001",
            "supplierArticle": "SUP-777",
            "_sku_source_field": "supplierArticle",
        }
        resolved = resolve_row_sku(row)
        self.assertEqual(resolved.get("sku"), "777001")
        self.assertEqual(resolved.get("source_kind"), "primary")
        self.assertFalse(bool(resolved.get("fallback_used")))

    def test_resolve_row_sku_marks_fallback_usage(self) -> None:
        row = {
            "supplierArticle": "SUP-AB-01",
            "_sku_source_field": "supplierArticle",
        }
        resolved = resolve_row_sku(row)
        self.assertEqual(resolved.get("sku"), "SUP-AB-01")
        self.assertEqual(resolved.get("source_kind"), "fallback")
        self.assertTrue(bool(resolved.get("fallback_used")))


class TestFinancialIntegrity(unittest.TestCase):
    def test_completeness_with_revenue_only_is_not_zero(self) -> None:
        integrity = evaluate_financial_integrity(
            totals={"total_revenue": 1500.0},
            data_sources={"revenue": "finance_report"},
            sku_attribution_status="ok",
            ads_rows_count=0,
        )
        self.assertEqual(int(integrity.get("available_components", 0)), 1)
        self.assertGreater(float(integrity.get("financial_completeness_pct", 0.0)), 0.0)
        self.assertEqual(str(integrity.get("financial_finality_status")), "sparse")

    def test_completeness_is_final_only_with_full_component_set(self) -> None:
        totals = {
            "total_revenue": 1000.0,
            "wb_commission": 100.0,
            "logistics": 50.0,
            "storage": 20.0,
            "penalties": 5.0,
            "deductions": 3.0,
            "cost_price": 400.0,
            "tax": 80.0,
            "ads_spend_total": 40.0,
        }
        sources = {
            "revenue": "finance_report",
            "commission": "finance_report",
            "logistics": "finance_report",
            "storage": "finance_report",
            "penalties": "finance_report",
            "deductions": "finance_report",
            "cost_price": "finance_report",
            "tax": "finance_report",
            "ads_spend": "ads_report",
        }
        integrity = evaluate_financial_integrity(
            totals=totals,
            data_sources=sources,
            sku_attribution_status="ok",
            ads_rows_count=10,
        )
        self.assertEqual(int(integrity.get("available_components", 0)), 9)
        self.assertEqual(float(integrity.get("financial_completeness_pct", 0.0)), 100.0)
        self.assertEqual(str(integrity.get("financial_finality_status")), "final")


class TestSkuAttributionIntegrity(unittest.TestCase):
    def test_parser_failure_with_sales_activity_is_broken_not_business_signal(self) -> None:
        sales_unassigned = [
            {"_sku_validation_reason": "parser_error", "revenue": 100.0, "cost_price": 50.0},
            {"_sku_validation_reason": "contains_invalid_chars", "revenue": 50.0, "cost_price": 20.0},
        ]
        integrity = evaluate_sku_attribution(
            valid_sku_count=0,
            sales_unassigned=sales_unassigned,
            ads_unassigned=[],
            stocks_unassigned=[],
            sales_activity_qty=5,
        )
        self.assertEqual(str(integrity.get("sku_attribution_status")), "broken")
        self.assertTrue(bool(integrity.get("attribution_guard_triggered")))
        self.assertEqual(int(integrity.get("invalid_sku_rows_parser_error", 0)), 2)

    def test_true_unassigned_is_separate_from_missing_field(self) -> None:
        sales_unassigned = [
            {"_sku_validation_reason": "missing_field", "revenue": 0.0, "cost_price": 120.0, "logistics": 10.0},
            {"_sku_validation_reason": "missing_field", "revenue": 0.0, "cost_price": 0.0, "logistics": 0.0},
        ]
        integrity = evaluate_sku_attribution(
            valid_sku_count=5,
            sales_unassigned=sales_unassigned,
            ads_unassigned=[],
            stocks_unassigned=[],
            sales_activity_qty=0,
        )
        self.assertEqual(int(integrity.get("unassigned_rows_true", 0)), 1)
        self.assertEqual(int(integrity.get("invalid_sku_rows_missing_field", 0)), 1)
        self.assertEqual(str(integrity.get("sku_attribution_status")), "degraded")


if __name__ == "__main__":
    unittest.main()
