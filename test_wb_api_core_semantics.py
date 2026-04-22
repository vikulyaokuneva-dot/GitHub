from __future__ import annotations

import unittest
from typing import Any, Dict, Iterable, List

from wb_api_core.artifacts import build_debug
from wb_api_core.loaders import load_cabinet_commerce, load_finance_final, load_orders, load_sales
from wb_api_core.normalize import normalize_bundle
from wb_api_core.reconcile import reconcile_bundle
from wb_api_core.snapshot import build_snapshot


class _FakeClient:
    def __init__(self, payloads: Dict[str, Any]) -> None:
        self.payloads = dict(payloads)
        self.calls: List[Dict[str, Any]] = []
        self.analytics_base_url = "https://seller-analytics-api.wildberries.ru"
        self.finance_base_url = "https://finance-api.wildberries.ru"
        self.statistics_base_url = "https://statistics-api.wildberries.ru"

    def request_json(
        self,
        *,
        endpoint_name: str,
        path: str,
        params: Dict[str, Any] | None = None,
        method: str = "GET",
        json_body: Any = None,
        allow_204: bool = False,
        empty_on_204: Any = None,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "endpoint_name": endpoint_name,
                "path": path,
                "params": dict(params or {}),
                "method": method,
                "json_body": json_body,
                "allow_204": allow_204,
                "empty_on_204": empty_on_204,
                "base_url": base_url,
            }
        )
        payload = self.payloads.get(endpoint_name, [])
        return {
            "endpoint": endpoint_name,
            "path": path,
            "success": True,
            "payload": payload,
            "error_text": "",
            "status_code": 200,
            "attempts": 1,
            "method": method,
            "base_url": base_url,
        }

    @staticmethod
    def extract_rows(payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []


def _raw_bundle_fixture() -> Dict[str, Any]:
    return {
        "cabinet_commerce": {
            "rows_raw": [
                {
                    "product": {
                        "nmId": 1001,
                        "vendorCode": "ART-1001",
                        "brandName": "Brand A",
                        "subjectId": 77,
                        "subjectName": "Subject A",
                        "title": "Product A",
                    },
                    "statistic": {
                        "selected": {
                            "period": {"start": "2026-04-21", "end": "2026-04-21"},
                            "orderCount": 2,
                            "orderSum": 1500.0,
                            "buyoutCount": 1,
                            "buyoutSum": 700.0,
                        }
                    },
                },
                {
                    "product": {
                        "nmId": 1002,
                        "vendorCode": "ART-1002",
                        "brandName": "Brand B",
                        "subjectId": 88,
                        "subjectName": "Subject B",
                        "title": "Product B",
                    },
                    "statistic": {
                        "selected": {
                            "period": {"start": "2026-04-21", "end": "2026-04-21"},
                            "orderCount": 3,
                            "orderSum": 2500.0,
                            "buyoutCount": 2,
                            "buyoutSum": 1800.0,
                        }
                    },
                },
            ],
            "debug": {"success": True},
        },
        "finance_final": {
            "rows_raw": [
                {
                    "saleDt": "2026-04-21T10:00:00Z",
                    "nmId": 1001,
                    "supplierArticle": "ART-1001",
                    "quantity": 1,
                    "retailAmount": 1800.0,
                    "retailPriceWithDisc": 1800.0,
                    "ppvzSalesCommission": 250.0,
                    "deliveryAmount": -90.0,
                    "paidStorage": -20.0,
                    "penalty": -5.0,
                    "deduction": -10.0,
                    "acquiringFee": -15.0,
                    "forPay": 1410.0,
                    "tax": 108.0,
                    "officeName": "Podolsk",
                    "docTypeName": "Продажа",
                }
            ],
            "debug": {"success": True},
        },
        "orders": {
            "rows_raw": [
                {
                    "date": "2026-04-21T09:00:00",
                    "lastChangeDate": "2026-04-21T09:15:00",
                    "nmId": 1001,
                    "srid": "order-1",
                    "quantity": 1,
                    "priceWithDisc": 800.0,
                }
            ],
            "debug": {"success": True},
        },
        "sales": {
            "rows_raw": [
                {
                    "date": "2026-04-21T12:00:00",
                    "nmId": 1001,
                    "saleID": "sale-1",
                    "quantity": 1,
                    "priceWithDisc": 700.0,
                }
            ],
            "debug": {"success": True},
        },
        "stocks": {
            "rows_raw": [
                {"date": "2026-04-21T15:00:00", "nmId": 1001, "quantityFull": 10, "warehouseName": "Podolsk"}
            ],
            "debug": {"success": True},
        },
    }


class TestWbApiCoreSemantics(unittest.TestCase):
    def test_load_cabinet_commerce_uses_analytics_host_and_period_body(self) -> None:
        client = _FakeClient(
            {
                "cabinet_commerce": {
                    "data": {
                        "products": [
                            {
                                "product": {"nmId": 1001},
                                "statistic": {"selected": {"period": {"start": "2026-04-21", "end": "2026-04-21"}}},
                            }
                        ]
                    }
                }
            }
        )

        bundle = load_cabinet_commerce(client, "2026-04-21")

        self.assertEqual(len(bundle["rows_raw"]), 1)
        self.assertEqual(client.calls[0]["base_url"], client.analytics_base_url)
        self.assertEqual(client.calls[0]["method"], "POST")
        self.assertEqual(client.calls[0]["json_body"]["selectedPeriod"], {"start": "2026-04-21", "end": "2026-04-21"})
        self.assertEqual(client.calls[0]["json_body"]["offset"], 0)

    def test_load_finance_final_uses_finance_host_and_daily_body(self) -> None:
        client = _FakeClient(
            {
                "finance_final": [
                    {
                        "saleDt": "2026-04-21T10:00:00Z",
                        "retailAmount": 1000.0,
                        "forPay": 800.0,
                    }
                ]
            }
        )

        bundle = load_finance_final(client, "2026-04-21")

        self.assertEqual(len(bundle["rows_raw"]), 1)
        self.assertEqual(client.calls[0]["base_url"], client.finance_base_url)
        self.assertEqual(client.calls[0]["method"], "POST")
        self.assertEqual(client.calls[0]["json_body"]["period"], "daily")
        self.assertEqual(client.calls[0]["json_body"]["limit"], 100000)
        self.assertEqual(client.calls[0]["json_body"]["rrdId"], 0)
        self.assertNotIn("fields", client.calls[0]["json_body"])

    def test_normalize_and_reconcile_keep_source_families_separate(self) -> None:
        raw_bundle = _raw_bundle_fixture()

        normalized = normalize_bundle(raw_bundle)
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )

        self.assertEqual(normalized["debug"]["counts"]["cabinet_commerce"], 2)
        self.assertEqual(normalized["debug"]["counts"]["finance_final"], 1)
        self.assertEqual(reconciled["cabinet_commerce_daily"]["orders_count"], 5.0)
        self.assertEqual(reconciled["cabinet_commerce_daily"]["orders_amount"], 4000.0)
        self.assertEqual(reconciled["cabinet_commerce_daily"]["buyouts_count"], 3.0)
        self.assertEqual(reconciled["cabinet_commerce_daily"]["buyouts_amount"], 2500.0)
        self.assertEqual(reconciled["finance_final_daily"]["gross_revenue"], 1800.0)
        self.assertEqual(reconciled["finance_final_daily"]["acquiring"], -15.0)
        self.assertEqual(reconciled["live_operational"]["orders"]["count"], 1.0)
        self.assertEqual(reconciled["live_operational"]["sales"]["amount"], 700.0)
        self.assertEqual(reconciled["live_operational"]["stocks"]["total_units"], 10.0)

    def test_finance_final_normalization_supports_new_detailed_field_names(self) -> None:
        raw_bundle = _raw_bundle_fixture()
        normalized = normalize_bundle(raw_bundle)
        finance_rows = normalized["finance_final_rows"]

        self.assertEqual(len(finance_rows), 1)
        self.assertEqual(finance_rows[0]["date"], "2026-04-21")
        self.assertEqual(finance_rows[0]["storage"], -20.0)
        self.assertEqual(finance_rows[0]["seller_payout"], 1410.0)

    def test_stocks_rows_are_aligned_to_single_snapshot_date(self) -> None:
        raw_bundle = _raw_bundle_fixture()
        raw_bundle["stocks"]["rows_raw"] = [
            {"lastChangeDate": "2026-04-21T10:00:00", "nmId": 1001, "quantityFull": 10, "warehouseName": "Podolsk"},
            {"lastChangeDate": "2026-04-22T09:00:00", "nmId": 1002, "quantityFull": 5, "warehouseName": "Kazan"},
            {"lastChangeDate": "2026-04-22T11:00:00", "nmId": 1003, "quantityFull": 7, "warehouseName": "Tula"},
        ]
        normalized = normalize_bundle(raw_bundle)
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )

        stock_rows = reconciled["live_operational"]["stocks"]["rows"]
        self.assertEqual(reconciled["live_operational"]["stocks"]["actual_date"], "2026-04-22")
        self.assertEqual(reconciled["live_operational"]["stocks"]["date_aligned"], False)
        self.assertEqual(reconciled["live_operational"]["stocks"]["total_units"], 22.0)
        self.assertTrue(all(str((row or {}).get("date") or "") == "2026-04-22" for row in stock_rows))

    def test_snapshot_and_debug_use_new_sections(self) -> None:
        raw_bundle = _raw_bundle_fixture()
        normalized = normalize_bundle(raw_bundle)
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )
        snapshot = build_snapshot(
            seller_id="seller_001",
            run_date="2026-04-21",
            operational_date="2026-04-21",
            timezone_name="Europe/Moscow",
            reconcile_result=reconciled,
        )
        debug = build_debug(
            seller_id="seller_001",
            run_date="2026-04-21",
            operational_date="2026-04-21",
            timezone_name="Europe/Moscow",
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            reconcile_result=reconciled,
        )

        self.assertEqual(snapshot["source_mode"], "wb_api_core_v2")
        self.assertEqual(snapshot["cabinet_commerce_daily"]["orders_count"], 5.0)
        self.assertEqual(snapshot["finance_final_daily"]["gross_revenue"], 1800.0)
        self.assertEqual(snapshot["live_operational"]["orders"]["count"], 1.0)
        self.assertEqual(snapshot["live_operational"]["stocks"]["actual_date"], "2026-04-21")
        self.assertIn("cabinet_commerce", debug["endpoints"])
        self.assertIn("finance_final", debug["endpoints"])
        self.assertEqual(debug["reconcile"]["selected_sources"]["cabinet_commerce_daily"], "sales_funnel_api")
        self.assertEqual(debug["counts"]["raw"]["cabinet_commerce"], 2)

    def test_live_operational_loaders_keep_statistics_host(self) -> None:
        client = _FakeClient(
            {
                "orders": [{"date": "2026-04-21T10:00:00", "nmId": 1001, "srid": "order-1"}],
                "sales": [{"date": "2026-04-21T11:00:00", "nmId": 1001, "saleID": "sale-1"}],
            }
        )

        load_orders(client, "2026-04-21")
        load_sales(client, "2026-04-21")

        self.assertEqual(client.calls[0]["base_url"], None)
        self.assertEqual(client.calls[1]["base_url"], None)
        self.assertEqual(client.calls[0]["params"], {"dateFrom": "2026-04-21", "flag": 0})
        self.assertEqual(client.calls[1]["params"], {"dateFrom": "2026-04-21", "flag": 1})


if __name__ == "__main__":
    unittest.main()
