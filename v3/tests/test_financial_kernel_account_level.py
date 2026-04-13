import unittest

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

        self.assertEqual(result.kernel_status, "account_level_ported_partial")
        self.assertFalse(bool(result.sku_financials))
        self.assertEqual(str(result.cogs_diagnostics.get("mode") or ""), "not_ported")
        self.assertEqual(int(result.cogs_diagnostics.get("cogs_rows_loaded", 0) or 0), 1)

    def test_empty_rows_and_partial_port_warnings(self) -> None:
        result = run_financial_kernel(FinancialKernelInput(realization_rows=[], tax_rate=0.06))
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}

        self.assertIn("financial_kernel_rows_empty", warning_codes)
        self.assertIn("financial_kernel_input_missing_groups", warning_codes)
        self.assertIn("financial_kernel_partial_port", warning_codes)
        self.assertEqual(result.kernel_status, "account_level_ported_partial")
        self.assertEqual(result.account_financial_totals.rows_count, 0)
        self.assertAlmostEqual(result.account_financial_totals.profit, 0.0, places=2)


if __name__ == "__main__":
    unittest.main()
