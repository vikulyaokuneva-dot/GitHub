import unittest
from dataclasses import asdict

from src.metrics import calc_financial_metrics
from v3.metrics import FinancialKernelInput, SKUFinancialRow, run_financial_kernel


SALE_OPERATION = "\u041f\u0440\u043e\u0434\u0430\u0436\u0430"
RETURN_OPERATION = "\u0412\u043e\u0437\u0432\u0440\u0430\u0442"
LOGISTICS_OPERATION = "\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430"


def _sku_row_dict(row: SKUFinancialRow) -> dict:
    return asdict(row)


class TestFinancialKernelSKUPnl(unittest.TestCase):
    def test_sku_sale_only(self) -> None:
        rows = [
            {
                "supplier_oper_name": SALE_OPERATION,
                "nm_id": 101,
                "quantity": 2,
                "retail_amount": 200.0,
                "ppvz_sales_commission": 20.0,
                "delivery_rub": -10.0,
                "storage_fee": -5.0,
                "penalty": -1.0,
                "ppvz_for_pay": 150.0,
            }
        ]
        result = run_financial_kernel(
            FinancialKernelInput(realization_rows=rows, tax_rate=0.0, cogs_rows=[], cogs_file_found=True)
        )

        self.assertIn(101, result.sku_financials)
        self.assertIsInstance(result.sku_financials[101], SKUFinancialRow)
        sku = result.sku_financials[101]
        self.assertEqual(sku.sales_qty, 2)
        self.assertEqual(sku.returns_qty, 0)
        self.assertAlmostEqual(sku.sales_revenue, 200.0, places=2)
        self.assertAlmostEqual(sku.returns_revenue_est, 0.0, places=2)
        self.assertAlmostEqual(sku.net_revenue, 200.0, places=2)
        self.assertAlmostEqual(sku.commission, 20.0, places=2)
        self.assertAlmostEqual(sku.logistics, 10.0, places=2)
        self.assertAlmostEqual(sku.storage, 5.0, places=2)
        self.assertAlmostEqual(sku.penalties, 1.0, places=2)
        self.assertAlmostEqual(sku.payout, 150.0, places=2)
        self.assertAlmostEqual(sku.tax_alloc, 0.0, places=2)
        self.assertAlmostEqual(sku.cogs, 0.0, places=2)
        self.assertAlmostEqual(sku.profit, 164.0, places=2)
        self.assertAlmostEqual(sku.margin, 0.82, places=4)

    def test_sku_sale_plus_return(self) -> None:
        rows = [
            {
                "supplier_oper_name": SALE_OPERATION,
                "nm_id": 102,
                "quantity": 1,
                "retail_amount": 100.0,
                "ppvz_sales_commission": 10.0,
            },
            {
                "supplier_oper_name": RETURN_OPERATION,
                "nm_id": 102,
                "quantity": -1,
                "retail_amount": 100.0,
                "ppvz_sales_commission": 2.0,
            },
        ]
        result = run_financial_kernel(
            FinancialKernelInput(realization_rows=rows, tax_rate=0.0, cogs_rows=[], cogs_file_found=True)
        )
        sku = result.sku_financials[102]

        self.assertEqual(sku.sales_qty, 1)
        self.assertEqual(sku.returns_qty, 1)
        self.assertAlmostEqual(sku.sales_revenue, 100.0, places=2)
        self.assertAlmostEqual(sku.returns_revenue_est, 100.0, places=2)
        self.assertAlmostEqual(sku.net_revenue, 0.0, places=2)
        self.assertAlmostEqual(sku.commission, 12.0, places=2)
        self.assertAlmostEqual(sku.profit, -12.0, places=2)
        self.assertAlmostEqual(sku.margin, 0.0, places=4)

    def test_sku_cogs_assignment(self) -> None:
        rows = [
            {
                "supplier_oper_name": SALE_OPERATION,
                "nm_id": 103,
                "quantity": 3,
                "retail_amount": 300.0,
            }
        ]
        cogs_rows = [{"sku": "103", "cogs": 20.0}]
        result = run_financial_kernel(
            FinancialKernelInput(realization_rows=rows, tax_rate=0.0, cogs_rows=cogs_rows, cogs_file_found=True)
        )
        sku = result.sku_financials[103]

        self.assertAlmostEqual(sku.cogs, 60.0, places=2)
        self.assertAlmostEqual(sku.profit, 240.0, places=2)

    def test_sku_tax_allocation(self) -> None:
        rows = [
            {"supplier_oper_name": SALE_OPERATION, "nm_id": 201, "quantity": 1, "retail_amount": 100.0},
            {"supplier_oper_name": SALE_OPERATION, "nm_id": 202, "quantity": 1, "retail_amount": 300.0},
        ]
        result = run_financial_kernel(
            FinancialKernelInput(realization_rows=rows, tax_rate=0.1, cogs_rows=[], cogs_file_found=True)
        )

        self.assertAlmostEqual(result.account_financial_totals.tax, 40.0, places=2)
        self.assertAlmostEqual(result.sku_financials[201].tax_alloc, 10.0, places=2)
        self.assertAlmostEqual(result.sku_financials[202].tax_alloc, 30.0, places=2)
        self.assertAlmostEqual(
            result.sku_financials[201].tax_alloc + result.sku_financials[202].tax_alloc,
            40.0,
            places=2,
        )

    def test_sku_profit_and_margin(self) -> None:
        rows = [
            {
                "supplier_oper_name": SALE_OPERATION,
                "nm_id": 301,
                "quantity": 2,
                "retail_amount": 1000.0,
                "ppvz_sales_commission": 100.0,
                "delivery_rub": -50.0,
                "storage_fee": -20.0,
                "penalty": -30.0,
            }
        ]
        cogs_rows = [{"sku": "301", "cogs": 150.0}]
        result = run_financial_kernel(
            FinancialKernelInput(realization_rows=rows, tax_rate=0.1, cogs_rows=cogs_rows, cogs_file_found=True)
        )
        sku = result.sku_financials[301]

        self.assertAlmostEqual(sku.profit, 400.0, places=2)
        self.assertAlmostEqual(sku.margin, 0.4, places=4)

    def test_sku_financials_parity_with_v2_subset(self) -> None:
        rows = [
            {
                "supplier_oper_name": SALE_OPERATION,
                "nm_id": 7001,
                "supplierArticle": "A-1",
                "quantity": 2,
                "retail_amount": 200.0,
                "ppvz_sales_commission": 20.0,
                "delivery_rub": -10.0,
                "ppvz_for_pay": 150.0,
            },
            {
                "supplier_oper_name": RETURN_OPERATION,
                "nm_id": 7001,
                "supplierArticle": "A-1",
                "quantity": -1,
                "retail_amount": 100.0,
                "ppvz_sales_commission": 5.0,
                "ppvz_for_pay": -70.0,
            },
            {
                "supplier_oper_name": SALE_OPERATION,
                "nm_id": 7002,
                "supplierArticle": "B-2",
                "quantity": 1,
                "retail_amount": 120.0,
                "ppvz_sales_commission": 12.0,
                "ppvz_for_pay": 90.0,
            },
            {
                "supplier_oper_name": LOGISTICS_OPERATION,
                "nm_id": 7002,
                "delivery_rub": -8.0,
                "rebill_logistic_cost": -2.0,
                "ppvz_for_pay": -5.0,
            },
        ]
        cogs_rows = [
            {"sku_token": "7001", "cogs": 30.0},
            {"seller_sku_token": "b-2", "cogs": 40.0},
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

        v2_sku = v2.get("sku_financials") if isinstance(v2.get("sku_financials"), dict) else {}
        v2_sku = {int(k): dict(v) for k, v in v2_sku.items()}
        v3_sku = {int(k): _sku_row_dict(v) for k, v in v3.sku_financials.items()}

        expected_fields = [
            "sales_qty",
            "returns_qty",
            "sales_revenue",
            "returns_revenue_est",
            "net_revenue",
            "commission",
            "logistics",
            "storage",
            "penalties",
            "payout",
            "tax_alloc",
            "cogs",
            "profit",
            "margin",
        ]

        self.assertEqual(set(v3_sku.keys()), set(v2_sku.keys()))
        for sku_id in sorted(v2_sku.keys()):
            self.assertIn(sku_id, v3_sku)
            for field in expected_fields:
                if field in {"sales_qty", "returns_qty"}:
                    self.assertEqual(
                        int(v3_sku[sku_id].get(field) or 0),
                        int(v2_sku[sku_id].get(field) or 0),
                    )
                else:
                    places = 4 if field == "margin" else 2
                    self.assertAlmostEqual(
                        float(v3_sku[sku_id].get(field) or 0.0),
                        float(v2_sku[sku_id].get(field) or 0.0),
                        places=places,
                    )


if __name__ == "__main__":
    unittest.main()
