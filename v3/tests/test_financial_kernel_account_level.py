import unittest

from src.metrics import calc_financial_metrics
from v3.metrics import FinancialKernelInput, run_financial_kernel


class TestFinancialKernelAccountLevel(unittest.TestCase):
    def test_account_level_totals_parity_without_cogs(self) -> None:
        rows = [
            {
                "supplier_oper_name": "Продажа",
                "quantity": 2,
                "retail_amount": 2000,
                "retail_price": 2400,
                "ppvz_sales_commission": 300,
                "delivery_rub": -100,
                "storage_fee": -20,
                "penalty": -5,
                "ppvz_for_pay": 1500,
            },
            {
                "supplier_oper_name": "Возврат",
                "quantity": -1,
                "retail_amount": 1000,
                "ppvz_sales_commission": 50,
                "delivery_rub": -40,
                "storage_fee": 0,
                "penalty": 2,
                "ppvz_for_pay": -700,
            },
            {
                "supplier_oper_name": "Логистика",
                "delivery_rub": -30,
                "rebill_logistic_cost": -10,
                "ppvz_for_pay": -20,
            },
            {
                "supplier_oper_name": "Хранение",
                "storage_fee": -15,
                "ppvz_for_pay": -5,
            },
            {
                "supplier_oper_name": "Штраф",
                "penalty": -7,
                "ppvz_for_pay": -7,
            },
            {
                "supplier_oper_name": "Удержание",
                "ppvz_sales_commission": 20,
                "payment_services_compensation": 12,
                "payment_services_compensation_amount": 8,
                "delivery_rub": -3,
                "storage_fee": -2,
                "penalty": -1,
                "ppvz_for_pay": -10,
            },
        ]

        result = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.06,
                cogs_rows=[{"sku": "111", "cogs": 99}],
                cogs_file_found=True,
                source_meta={"orders_source": "api", "buyouts_source": "api"},
            )
        )

        totals = result.account_financial_totals
        self.assertEqual(totals.rows_count, 6)
        self.assertEqual(totals.sales_qty, 2)
        self.assertEqual(totals.returns_qty, 1)
        self.assertAlmostEqual(totals.gross_revenue, 2000.00, places=2)
        self.assertAlmostEqual(float(totals.turnover_wb or 0.0), 2400.00, places=2)
        self.assertEqual(totals.turnover_wb_rows_count, 1)

        # Sign handling: these expenses must be aggregated as positive magnitudes.
        self.assertAlmostEqual(totals.commission, 390.00, places=2)
        self.assertAlmostEqual(totals.logistics, 183.00, places=2)
        self.assertAlmostEqual(totals.storage, 37.00, places=2)
        self.assertAlmostEqual(totals.penalties, 15.00, places=2)
        # Payout keeps original sign.
        self.assertAlmostEqual(totals.payout, 758.00, places=2)

        self.assertAlmostEqual(totals.tax, 120.00, places=2)
        self.assertAlmostEqual(totals.profit, 1255.00, places=2)
        self.assertAlmostEqual(totals.margin, 0.6275, places=4)
        self.assertAlmostEqual(totals.cogs_total, 0.0, places=2)

        breakdown = result.commission_breakdown
        self.assertAlmostEqual(breakdown.base_commission, 370.00, places=2)
        self.assertAlmostEqual(breakdown.payment_services_compensation, 12.00, places=2)
        self.assertAlmostEqual(breakdown.payment_services_compensation_amount, 8.00, places=2)
        self.assertAlmostEqual(breakdown.total_commission, 390.00, places=2)

        self.assertEqual(result.kernel_status, "account_and_cogs_ported_partial")
        self.assertFalse(bool(result.sku_financials))
        self.assertEqual(str(result.cogs_diagnostics.get("mode") or ""), "v2_parity_account_level")
        self.assertEqual(int(result.cogs_diagnostics.get("cogs_rows_loaded", 0) or 0), 1)
        self.assertTrue(bool(result.cogs_diagnostics.get("cogs_ported")))

    def test_empty_rows_and_partial_port_warnings(self) -> None:
        result = run_financial_kernel(FinancialKernelInput(realization_rows=[], tax_rate=0.06))
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}

        self.assertIn("financial_kernel_rows_empty", warning_codes)
        self.assertIn("financial_kernel_input_missing_groups", warning_codes)
        self.assertIn("financial_kernel_partial_port", warning_codes)
        self.assertEqual(result.kernel_status, "account_and_cogs_ported_partial")
        self.assertEqual(result.account_financial_totals.rows_count, 0)
        self.assertAlmostEqual(result.account_financial_totals.profit, 0.0, places=2)

    def test_cogs_full_match_updates_cogs_total_and_profit(self) -> None:
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        rows = [
            {"supplier_oper_name": sale, "nm_id": 1001, "quantity": 2, "retail_amount": 200.0},
            {"supplier_oper_name": sale, "nm_id": 1002, "quantity": 1, "retail_amount": 100.0},
        ]
        result = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.0,
                cogs_rows=[
                    {"sku": "1001", "cogs": 10.0},
                    {"sku": "1002", "cogs": 20.0},
                ],
                cogs_file_found=True,
            )
        )
        totals = result.account_financial_totals
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}

        self.assertAlmostEqual(totals.gross_revenue, 300.0, places=2)
        self.assertAlmostEqual(totals.cogs_total, 40.0, places=2)
        self.assertAlmostEqual(totals.profit, 260.0, places=2)
        self.assertEqual(str(result.cogs_diagnostics.get("cogs_status") or ""), "full_match")
        self.assertAlmostEqual(float(result.cogs_diagnostics.get("coverage_ratio") or 0.0), 1.0, places=4)
        self.assertNotIn("cogs_partial_matches", warning_codes)
        self.assertNotIn("cogs_no_matches", warning_codes)

    def test_cogs_partial_match_warning_and_coverage(self) -> None:
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        rows = [
            {"supplier_oper_name": sale, "nm_id": 2001, "quantity": 2, "retail_amount": 200.0},
            {"supplier_oper_name": sale, "nm_id": 2002, "quantity": 1, "retail_amount": 100.0},
        ]
        result = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.0,
                cogs_rows=[{"sku": "2001", "cogs": 10.0}],
                cogs_file_found=True,
            )
        )
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}
        totals = result.account_financial_totals

        self.assertEqual(str(result.cogs_diagnostics.get("cogs_status") or ""), "partial_match")
        self.assertIn("cogs_partial_matches", warning_codes)
        self.assertAlmostEqual(totals.cogs_total, 20.0, places=2)
        self.assertAlmostEqual(float(result.cogs_diagnostics.get("coverage_ratio") or 0.0), 0.5, places=4)

    def test_cogs_file_missing_warning(self) -> None:
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        rows = [{"supplier_oper_name": sale, "nm_id": 3001, "quantity": 1, "retail_amount": 100.0}]
        result = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.0,
                cogs_rows=None,
                cogs_file_found=False,
            )
        )
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}
        self.assertEqual(str(result.cogs_diagnostics.get("cogs_status") or ""), "file_not_found")
        self.assertIn("cogs_file_missing", warning_codes)
        self.assertAlmostEqual(result.account_financial_totals.cogs_total, 0.0, places=2)

    def test_cogs_file_exists_but_empty_warning(self) -> None:
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        rows = [{"supplier_oper_name": sale, "nm_id": 4001, "quantity": 1, "retail_amount": 100.0}]
        result = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.0,
                cogs_rows=[],
                cogs_file_found=True,
            )
        )
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}
        self.assertEqual(str(result.cogs_diagnostics.get("cogs_status") or ""), "file_found_not_read")
        self.assertIn("cogs_rows_empty", warning_codes)
        self.assertAlmostEqual(result.account_financial_totals.cogs_total, 0.0, places=2)

    def test_parity_against_v2_account_level_subset(self) -> None:
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        ret = "\u0412\u043e\u0437\u0432\u0440\u0430\u0442"
        log = "\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430"

        rows = [
            {
                "supplier_oper_name": sale,
                "quantity": 1,
                "retail_amount": 100.0,
                "retail_price": 120.0,
                "payment_services_compensation_amount": 10.0,
                "ppvz_for_pay": 90.0,
            },
            {
                "supplier_oper_name": ret,
                "quantity": -1,
                "retail_amount": 70.0,
                "ppvz_sales_commission": 5.0,
                "ppvz_for_pay": -60.0,
            },
            {
                "supplier_oper_name": log,
                "rebill_logistic_cost": -15.0,
                "ppvz_for_pay": -15.0,
            },
            {
                "supplier_oper_name": "sale",
                "quantity": 3,
                "retail_amount": 300.0,
                "ppvz_sales_commission": 30.0,
                "ppvz_for_pay": 250.0,
            },
        ]

        v2 = calc_financial_metrics(rows, tax_rate=0.06, cogs_rows=[], cogs_file_found=True)
        v3 = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.06,
                cogs_rows=[],
                cogs_file_found=True,
            )
        )
        totals = v3.account_financial_totals

        self.assertEqual(totals.rows_count, int(v2.get("rows_count") or 0))
        self.assertEqual(totals.sales_qty, int(v2.get("sales_qty") or 0))
        self.assertEqual(totals.returns_qty, int(v2.get("returns_qty") or 0))
        self.assertAlmostEqual(totals.gross_revenue, float(v2.get("gross_revenue") or 0.0), places=2)
        self.assertAlmostEqual(float(totals.turnover_wb or 0.0), float(v2.get("turnover_wb") or 0.0), places=2)
        self.assertEqual(totals.turnover_wb_rows_count, int(v2.get("turnover_wb_rows_count") or 0))
        self.assertAlmostEqual(totals.commission, float(v2.get("commission") or 0.0), places=2)
        self.assertAlmostEqual(totals.logistics, float(v2.get("logistics") or 0.0), places=2)
        self.assertAlmostEqual(totals.storage, float(v2.get("storage") or 0.0), places=2)
        self.assertAlmostEqual(totals.penalties, float(v2.get("penalties") or 0.0), places=2)
        self.assertAlmostEqual(totals.payout, float(v2.get("payout") or 0.0), places=2)
        self.assertAlmostEqual(totals.tax, float(v2.get("tax") or 0.0), places=2)
        self.assertAlmostEqual(totals.profit, float(v2.get("profit") or 0.0), places=2)
        self.assertAlmostEqual(totals.margin, float(v2.get("margin") or 0.0), places=4)

        breakdown = v3.commission_breakdown
        v2_breakdown = v2.get("commission_breakdown") if isinstance(v2.get("commission_breakdown"), dict) else {}
        self.assertAlmostEqual(breakdown.base_commission, float(v2_breakdown.get("base_commission") or 0.0), places=2)
        self.assertAlmostEqual(breakdown.pvz_compensation, float(v2_breakdown.get("pvz_compensation") or 0.0), places=2)
        self.assertAlmostEqual(
            breakdown.payment_services_compensation,
            float(v2_breakdown.get("payment_services_compensation") or 0.0),
            places=2,
        )
        self.assertAlmostEqual(
            breakdown.payment_services_compensation_amount,
            float(v2_breakdown.get("payment_services_compensation_amount") or 0.0),
            places=2,
        )
        self.assertAlmostEqual(breakdown.total_commission, float(v2_breakdown.get("total_commission") or 0.0), places=2)

    def test_parity_against_v2_with_cogs_matching(self) -> None:
        sale = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
        rows = [
            {
                "supplier_oper_name": sale,
                "nm_id": 5001,
                "quantity": 2,
                "retail_amount": 220.0,
                "supplierArticle": "ABC-1",
            },
            {
                "supplier_oper_name": sale,
                "nm_id": 5002,
                "quantity": 1,
                "retail_amount": 140.0,
                "supplierArticle": "XYZ-2",
            },
        ]
        cogs_rows = [
            {"sku_token": "5001", "cogs": 50.0},
            {"seller_sku_token": "xyz-2", "cogs": 30.0},
        ]

        v2 = calc_financial_metrics(rows, tax_rate=0.06, cogs_rows=cogs_rows, cogs_file_found=True)
        v3 = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=rows,
                tax_rate=0.06,
                cogs_rows=cogs_rows,
                cogs_file_found=True,
            )
        )
        totals = v3.account_financial_totals
        v2_diag = v2.get("cogs_diagnostics") if isinstance(v2.get("cogs_diagnostics"), dict) else {}
        v3_diag = v3.cogs_diagnostics

        self.assertAlmostEqual(totals.cogs_total, float(v2.get("cogs_total") or 0.0), places=2)
        self.assertAlmostEqual(totals.profit, float(v2.get("profit") or 0.0), places=2)
        self.assertEqual(str(v3_diag.get("cogs_status") or ""), str(v2.get("cogs_status") or ""))
        self.assertEqual(int(v3_diag.get("cogs_rows_loaded") or 0), int(v2_diag.get("cogs_rows_loaded") or 0))
        self.assertEqual(int(v3_diag.get("cogs_matched_sku") or 0), int(v2_diag.get("cogs_matched_sku") or 0))


if __name__ == "__main__":
    unittest.main()
