import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from v3.ingestion.api_realization_loader import load_realization_from_api
from v3.metrics import FinancialKernelInput, run_financial_kernel
from v3.pipeline.daily_metrics_stage import run_daily_metrics_stage


class _RouterApiClient:
    def __init__(self, routes: Dict[Tuple[str, str], Dict[str, Any]]) -> None:
        self.routes = routes
        self.calls: List[Dict[str, Any]] = []

    def request_json(
        self,
        endpoint: Any,
        params: Dict[str, Any] | None = None,
        method: str = "GET",
        json_body: Any = None,
        **_: Any,
    ) -> Dict[str, Any]:
        method_token = str(method or "GET").strip().upper()
        path = str(getattr(endpoint, "path", "") or "")
        self.calls.append(
            {
                "endpoint": str(getattr(endpoint, "name", "") or ""),
                "path": path,
                "method": method_token,
                "params": params or {},
                "json_body": json_body,
            }
        )
        response = self.routes.get((method_token, path))
        if isinstance(response, dict):
            return dict(response)
        return {
            "success": False,
            "payload": {},
            "error": f"route_not_found:{method_token}:{path}",
            "status_code": 599,
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


def _new_finance_sale_row() -> Dict[str, Any]:
    return {
        "date": "2026-04-13T10:00:00",
        "nmId": "111",
        "supplierArticle": "ART-111",
        "title": "Тестовый товар",
        "brand": "Brand A",
        "subject": "Subject A",
        "supplierOperName": "Продажа",
        "supplierOperTypeName": "Продажа",
        "quantity": "2",
        "retailAmount": "2000.50",
        "retailPriceWithDiscRub": "1000.25",
        "retailPrice": "2200.00",
        "ppvzSalesCommission": "300.10",
        "deliveryRub": "-100.40",
        "storageFee": "-20.20",
        "penaltyAmount": "-5.00",
        "deduction": "-10.10",
        "ppvzForPay": "1564.70",
        "tax": "120.03",
    }


class TestFinanceRealizationMigration(unittest.TestCase):
    def test_new_finance_detailed_maps_to_internal_schema(self) -> None:
        client = _RouterApiClient(
            {
                ("POST", "/api/finance/v1/sales-reports/detailed"): {
                    "success": True,
                    "payload": {"data": [_new_finance_sale_row()]},
                    "error": "",
                    "status_code": 200,
                    "attempts": 1,
                }
            }
        )

        bundle = load_realization_from_api(client, date_from="2026-04-13", date_to="2026-04-13")
        rows = list(bundle.get("rows", []))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(str(row.get("sku") or ""), "111")
        self.assertEqual(str(row.get("nm_id") or ""), "111")
        self.assertEqual(str(row.get("title") or ""), "Тестовый товар")
        self.assertEqual(str(row.get("brand") or ""), "Brand A")
        self.assertEqual(str(row.get("subject") or ""), "Subject A")
        self.assertAlmostEqual(float(row.get("revenue") or 0.0), 2000.5, places=2)
        self.assertAlmostEqual(float(row.get("wb_commission") or 0.0), 300.1, places=2)
        self.assertAlmostEqual(float(row.get("logistics") or 0.0), -100.4, places=2)
        self.assertAlmostEqual(float(row.get("storage") or 0.0), -20.2, places=2)
        self.assertAlmostEqual(float(row.get("deductions") or 0.0), -10.1, places=2)
        self.assertAlmostEqual(float(row.get("seller_payout") or 0.0), 1564.7, places=2)
        api_debug = bundle.get("api_debug", {})
        self.assertEqual(str(api_debug.get("finance_api_mode") or ""), "new")
        self.assertEqual(str(api_debug.get("finance_endpoint_used") or ""), "/api/finance/v1/sales-reports/detailed")

    def test_empty_and_invalid_money_values_are_normalized_safely(self) -> None:
        row = _new_finance_sale_row()
        row.update(
            {
                "retailAmount": "",
                "retailPriceWithDiscRub": "",
                "retailPrice": "",
                "ppvzSalesCommission": None,
                "deliveryRub": "",
                "storageFee": "oops",
                "deduction": None,
                "ppvzForPay": "",
            }
        )
        client = _RouterApiClient(
            {
                ("POST", "/api/finance/v1/sales-reports/detailed"): {
                    "success": True,
                    "payload": {"data": [row]},
                    "error": "",
                    "status_code": 200,
                    "attempts": 1,
                }
            }
        )

        bundle = load_realization_from_api(client, date_from="2026-04-13", date_to="2026-04-13")
        parsed = list(bundle.get("rows", []))[0]
        self.assertEqual(float(parsed.get("revenue") or 0.0), 0.0)
        self.assertEqual(float(parsed.get("wb_commission") or 0.0), 0.0)
        self.assertEqual(float(parsed.get("logistics") or 0.0), 0.0)
        self.assertEqual(float(parsed.get("storage") or 0.0), 0.0)
        self.assertEqual(float(parsed.get("seller_payout") or 0.0), 0.0)
        mapping_diag = (
            bundle.get("api_debug", {}).get("finance_mapping_diagnostics", {})
            if isinstance(bundle.get("api_debug"), dict)
            else {}
        )
        self.assertGreaterEqual(int(mapping_diag.get("parse_errors_count", 0) or 0), 1)

    def test_primary_new_finance_path_does_not_call_legacy(self) -> None:
        client = _RouterApiClient(
            {
                ("POST", "/api/finance/v1/sales-reports/detailed"): {
                    "success": True,
                    "payload": {"data": [_new_finance_sale_row()]},
                    "error": "",
                    "status_code": 200,
                    "attempts": 1,
                },
                ("GET", "/api/v5/supplier/reportDetailByPeriod"): {
                    "success": False,
                    "payload": {"data": []},
                    "error": "legacy_should_not_be_called",
                    "status_code": 500,
                    "attempts": 1,
                },
            }
        )

        bundle = load_realization_from_api(client, date_from="2026-04-13", date_to="2026-04-13")
        api_debug = bundle.get("api_debug", {})
        self.assertEqual(str(api_debug.get("finance_api_mode") or ""), "new")
        self.assertTrue(all(str(call.get("path") or "") != "/api/v5/supplier/reportDetailByPeriod" for call in client.calls))

    def test_fallback_to_legacy_when_new_finance_fails(self) -> None:
        client = _RouterApiClient(
            {
                ("POST", "/api/finance/v1/sales-reports/detailed"): {
                    "success": False,
                    "payload": {},
                    "error": "finance_endpoint_unavailable",
                    "status_code": 503,
                    "attempts": 1,
                },
                ("GET", "/api/v5/supplier/reportDetailByPeriod"): {
                    "success": True,
                    "payload": {
                        "data": [
                            {
                                "date": "2026-04-13T10:00:00",
                                "nmId": 111,
                                "supplierArticle": "ART-111",
                                "supplier_oper_name": "Продажа",
                                "quantity": 1,
                                "retail_amount": 1000.0,
                                "ppvz_sales_commission": 120.0,
                                "delivery_rub": -40.0,
                                "ppvz_for_pay": 840.0,
                            }
                        ]
                    },
                    "error": "",
                    "status_code": 200,
                    "attempts": 1,
                },
            }
        )

        bundle = load_realization_from_api(client, date_from="2026-04-13", date_to="2026-04-13")
        rows = list(bundle.get("rows", []))
        self.assertEqual(len(rows), 1)
        api_debug = bundle.get("api_debug", {})
        self.assertEqual(str(api_debug.get("finance_api_mode") or ""), "legacy_fallback")
        self.assertEqual(str(api_debug.get("finance_endpoint_used") or ""), "/api/v5/supplier/reportDetailByPeriod")
        self.assertIn("finance_endpoint_unavailable", str(api_debug.get("finance_primary_error_text") or ""))
        called_paths = [str(call.get("path") or "") for call in client.calls]
        self.assertIn("/api/finance/v1/sales-reports/detailed", called_paths)
        self.assertIn("/api/v5/supplier/reportDetailByPeriod", called_paths)

    def test_downstream_financial_kernel_parity_for_new_finance_rows(self) -> None:
        sale = _new_finance_sale_row()
        returns = dict(sale)
        returns.update(
            {
                "date": "2026-04-13T11:00:00",
                "supplierOperName": "Возврат",
                "supplierOperTypeName": "Возврат",
                "quantity": "-1",
                "retailAmount": "1000.25",
                "ppvzSalesCommission": "50.00",
                "deliveryRub": "-40.00",
                "storageFee": "0",
                "ppvzForPay": "-700.00",
            }
        )
        client = _RouterApiClient(
            {
                ("POST", "/api/finance/v1/sales-reports/detailed"): {
                    "success": True,
                    "payload": {"data": [sale, returns]},
                    "error": "",
                    "status_code": 200,
                    "attempts": 1,
                }
            }
        )

        rows = load_realization_from_api(client, date_from="2026-04-13", date_to="2026-04-13").get("rows", [])
        kernel = run_financial_kernel(
            FinancialKernelInput(
                realization_rows=list(rows),
                tax_rate=0.06,
                cogs_rows=[{"sku": "111", "cogs": 100.0}],
                cogs_file_found=True,
            )
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = str(Path(tmp_dir) / "out")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ctx = run_daily_metrics_stage(
                {
                    "repo_root": "",
                    "seller_id": "seller_finance_migration",
                    "run_date": "2026-04-13",
                    "seller_name": "Seller Finance Migration",
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
                    "api_debug": {
                        "realization_rows": len(rows),
                        "financial_rows": len(rows),
                        "date_from": "2026-04-13",
                        "date_to": "2026-04-13",
                        "realization_actual_source_date": "2026-04-13",
                        "realization_fallback_used": False,
                        "realization_fallback_lag_days": 0,
                    },
                }
            )

        financial_kpi = ctx.get("financial_kpi", {})
        totals = kernel.account_financial_totals
        self.assertAlmostEqual(float(financial_kpi.get("gross_revenue") or 0.0), float(totals.gross_revenue), places=2)
        self.assertAlmostEqual(float(financial_kpi.get("wb_commission") or 0.0), float(totals.commission), places=2)
        self.assertAlmostEqual(float(financial_kpi.get("seller_payout") or 0.0), float(totals.payout), places=2)
        self.assertAlmostEqual(float(financial_kpi.get("logistics") or 0.0), float(totals.logistics), places=2)
        self.assertAlmostEqual(float(financial_kpi.get("storage") or 0.0), float(totals.storage), places=2)


if __name__ == "__main__":
    unittest.main()
