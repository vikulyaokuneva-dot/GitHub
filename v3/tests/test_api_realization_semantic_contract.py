import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v3.ingestion.api_realization_loader import load_realization_from_api
from v3.metrics import FinancialKernelInput, run_financial_kernel
from v3.pipeline.daily_metrics_stage import run_daily_metrics_stage


class _FakeApiClient:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = list(rows)

    def request_json(self, endpoint: Any, params: Dict[str, Any] | None = None, **_: Any) -> Dict[str, Any]:
        return {
            "success": True,
            "payload": {"data": list(self._rows)},
            "error": "",
            "status_code": 200,
            "attempts": 1,
        }

    def extract_rows(self, payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return []


def _api_realization_rows_fixture() -> List[Dict[str, Any]]:
    return [
        {
            "date": "2026-04-13T10:00:00",
            "nmId": 111,
            "supplierArticle": "ART-111",
            "supplierOperName": "\u041f\u0440\u043e\u0434\u0430\u0436\u0430",
            "quantity": 2,
            "retailAmount": 2000.0,
            "retailPriceWithDiscRub": 1000.0,
            "retailPrice": 2400.0,
            "ppvzSalesCommission": 300.0,
            "deliveryRub": -100.0,
            "storageFee": -20.0,
            "penaltyAmount": -5.0,
            "ppvzForPay": 1500.0,
        },
        {
            "date": "2026-04-13T11:00:00",
            "nmId": 111,
            "supplierArticle": "ART-111",
            "supplierOperName": "\u0412\u043e\u0437\u0432\u0440\u0430\u0442",
            "quantity": -1,
            "retailAmount": 1000.0,
            "ppvzSalesCommission": 50.0,
            "deliveryRub": -40.0,
            "ppvzForPay": -700.0,
        },
        {
            "date": "2026-04-13T12:00:00",
            "supplierOperName": "\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430",
            "deliveryRub": -30.0,
            "ppvzForPay": -20.0,
        },
    ]


class TestApiRealizationSemanticContract(unittest.TestCase):
    def test_loader_maps_kernel_semantic_fields(self) -> None:
        bundle = load_realization_from_api(
            _FakeApiClient(_api_realization_rows_fixture()),
            date_from="2026-04-13",
            date_to="2026-04-13",
        )
        rows = list(bundle.get("rows", []))
        self.assertEqual(len(rows), 3)

        sale = rows[0]
        self.assertEqual(str(sale.get("supplier_oper_name") or ""), "\u041f\u0440\u043e\u0434\u0430\u0436\u0430")
        self.assertAlmostEqual(float(sale.get("retail_amount") or 0.0), 2000.0, places=2)
        self.assertAlmostEqual(float(sale.get("ppvz_sales_commission") or 0.0), 300.0, places=2)
        self.assertAlmostEqual(float(sale.get("ppvz_for_pay") or 0.0), 1500.0, places=2)
        self.assertAlmostEqual(float(sale.get("delivery_rub") or 0.0), -100.0, places=2)
        self.assertAlmostEqual(float(sale.get("storage_fee") or 0.0), -20.0, places=2)
        self.assertEqual(str(sale.get("supplierArticle") or ""), "ART-111")

    def test_kernel_gets_required_semantic_groups_from_api_rows(self) -> None:
        rows = load_realization_from_api(
            _FakeApiClient(_api_realization_rows_fixture()),
            date_from="2026-04-13",
            date_to="2026-04-13",
        ).get("rows", [])
        result = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=list(rows),
                tax_rate=0.06,
                cogs_rows=[{"sku": "111", "cogs": 100.0}],
                cogs_file_found=True,
            )
        )

        validation = result.cogs_diagnostics.get("validation", {}) if isinstance(result.cogs_diagnostics, dict) else {}
        self.assertEqual(list(validation.get("missing_required_groups", [])), [])
        self.assertAlmostEqual(result.account_financial_totals.gross_revenue, 2000.0, places=2)
        self.assertGreater(result.account_financial_totals.commission, 0.0)
        self.assertNotEqual(result.account_financial_totals.payout, 0.0)
        self.assertGreater(result.account_financial_totals.logistics, 0.0)
        self.assertNotEqual(
            round(float(result.account_financial_totals.profit or 0.0), 2),
            round(float(-result.account_financial_totals.logistics or 0.0), 2),
        )
        warning_codes = {str(item.get("code") or "") for item in result.warnings if isinstance(item, dict)}
        self.assertNotIn("financial_kernel_input_missing_groups", warning_codes)

    def test_active_metrics_flow_uses_kernel_financials_for_api_rows(self) -> None:
        rows = load_realization_from_api(
            _FakeApiClient(_api_realization_rows_fixture()),
            date_from="2026-04-13",
            date_to="2026-04-13",
        ).get("rows", [])

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = str(Path(tmp_dir) / "out")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ctx = run_daily_metrics_stage(
                {
                    "repo_root": "",
                    "seller_id": "seller_api_semantics",
                    "run_date": "2026-04-13",
                    "seller_name": "Seller API",
                    "out_dir": out_dir,
                    "token": "token",
                    "source_mode": "wb_api",
                    "cfg": {"tax_rate": 0.06},
                    "sales_rows": list(rows),
                    "ads_rows": [],
                    "stocks_rows": [],
                    "api_orders_rows": [],
                    "api_sales_rows": [],
                    "api_realization_rows": list(rows),
                    "api_stocks_rows": [],
                    "supplier_goods_daily": {},
                    "cogs_rows": [{"sku": "111", "cogs": 100.0}],
                    "cogs_file_found": True,
                    "discovered_files": {},
                    "input_debug": {},
                    "api_debug": {"realization_rows": len(rows), "financial_rows": len(rows)},
                }
            )

        financial_kpi = ctx.get("financial_kpi", {})
        self.assertGreater(float(financial_kpi.get("gross_revenue", 0.0) or 0.0), 0.0)
        self.assertGreater(float(financial_kpi.get("wb_commission", 0.0) or 0.0), 0.0)
        self.assertNotEqual(float(financial_kpi.get("seller_payout", 0.0) or 0.0), 0.0)
        self.assertGreater(float(financial_kpi.get("logistics", 0.0) or 0.0), 0.0)
        self.assertNotEqual(
            round(float(financial_kpi.get("gross_revenue", 0.0) or 0.0), 2),
            round(float(financial_kpi.get("seller_payout", 0.0) or 0.0), 2),
        )
        self.assertFalse(bool(financial_kpi.get("kernel_semantic_mapping_missing", False)))
        self.assertEqual(list(financial_kpi.get("kernel_semantic_missing_groups", [])), [])
        self.assertNotEqual(
            round(float(financial_kpi.get("net_profit", 0.0) or 0.0), 2),
            round(float(-financial_kpi.get("logistics", 0.0) or 0.0), 2),
        )

    def test_financial_status_degraded_when_semantic_groups_are_missing(self) -> None:
        rows = [
            {
                "date": "2026-04-13",
                "nm_id": "111",
                "quantity": 1,
                "ppvz_for_pay": 100.0,
                "delivery_rub": -10.0,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = str(Path(tmp_dir) / "out")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ctx = run_daily_metrics_stage(
                {
                    "repo_root": "",
                    "seller_id": "seller_api_missing_semantics",
                    "run_date": "2026-04-13",
                    "seller_name": "Seller API",
                    "out_dir": out_dir,
                    "token": "token",
                    "source_mode": "wb_api",
                    "cfg": {"tax_rate": 0.06},
                    "sales_rows": list(rows),
                    "ads_rows": [],
                    "stocks_rows": [],
                    "api_orders_rows": [],
                    "api_sales_rows": [],
                    "api_realization_rows": list(rows),
                    "api_stocks_rows": [],
                    "supplier_goods_daily": {},
                    "cogs_rows": [{"sku": "111", "cogs": 10.0}],
                    "cogs_file_found": True,
                    "discovered_files": {},
                    "input_debug": {},
                    "api_debug": {"realization_rows": len(rows), "financial_rows": len(rows)},
                }
            )

        financial_kpi = ctx.get("financial_kpi", {})
        self.assertEqual(str(financial_kpi.get("financial_status") or ""), "degraded")
        self.assertEqual(str(financial_kpi.get("financial_finality_status") or ""), "unavailable")
        self.assertTrue(bool(financial_kpi.get("kernel_semantic_mapping_missing", False)))
        missing_groups = [str(item) for item in list(financial_kpi.get("kernel_semantic_missing_groups", []))]
        self.assertIn("operation_name", missing_groups)
        self.assertIn("row_amount", missing_groups)


if __name__ == "__main__":
    unittest.main()
