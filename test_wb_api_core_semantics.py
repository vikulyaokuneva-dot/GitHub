from __future__ import annotations

import json
import os
import tempfile
import unittest
from typing import Any, Dict, Iterable, List
from unittest.mock import MagicMock, patch

from wb_api_core.artifacts import build_debug
from wb_api_core.client import WBApiClient
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
        retry_policy: Dict[str, Any] | None = None,
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
                "retry_policy": dict(retry_policy or {}),
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
            "retry_count": 0,
            "retry_delays": [],
            "final_failure_reason": "",
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


class _AlwaysFailClient(_FakeClient):
    def __init__(self, *, status_code: int = 429, error_text: str = "429: too many requests") -> None:
        super().__init__({})
        self.status_code = status_code
        self.error_text = error_text

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
        retry_policy: Dict[str, Any] | None = None,
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
                "retry_policy": dict(retry_policy or {}),
            }
        )
        return {
            "endpoint": endpoint_name,
            "path": path,
            "success": False,
            "payload": None,
            "error_text": self.error_text,
            "status_code": self.status_code,
            "attempts": 5,
            "retry_count": 4,
            "retry_delays": [3.0, 6.0, 12.0, 24.0],
            "final_failure_reason": self.error_text,
            "method": method,
            "base_url": base_url,
        }


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
        self.assertEqual(client.calls[0]["retry_policy"]["max_attempts"], 5)

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
        # Test funnel_daily aggregation from same cabinet_commerce_rows
        # Note: test fixture doesn't include openCount/cartCount, so they're 0
        self.assertEqual(reconciled["funnel_daily"]["open_count"], 0.0)
        self.assertEqual(reconciled["funnel_daily"]["cart_count"], 0.0)
        self.assertEqual(reconciled["funnel_daily"]["orders_count"], 5.0)
        self.assertEqual(reconciled["funnel_daily"]["orders_amount"], 4000.0)
        self.assertEqual(reconciled["funnel_daily"]["buyouts_count"], 3.0)
        self.assertEqual(reconciled["funnel_daily"]["buyouts_amount"], 2500.0)
        self.assertEqual(reconciled["funnel_daily"]["available"], True)
        self.assertEqual(reconciled["funnel_daily"]["source"], "sales_funnel_api")
        self.assertEqual(reconciled["funnel_daily"]["owner_block"], "funnel_daily")
        # Status should be "partial" because we have lower funnel but no upper funnel
        self.assertEqual(reconciled["funnel_daily"]["status"], "partial")
        self.assertEqual(reconciled["funnel_daily"]["upper_funnel_status"], "unavailable")
        self.assertEqual(reconciled["funnel_daily"]["lower_funnel_status"], "ok")
        # Verify rates are None when denominator is 0
        self.assertIsNone(reconciled["funnel_daily"]["open_to_cart_rate"])
        self.assertIsNone(reconciled["funnel_daily"]["cart_to_order_rate"])
        self.assertAlmostEqual(reconciled["funnel_daily"]["order_to_buyout_rate"], 60.0, places=1)
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

    def test_finance_final_uses_report_date_and_excludes_zero_reimbursements(self) -> None:
        raw_bundle = _raw_bundle_fixture()
        raw_bundle["finance_final"]["rows_raw"] = [
            {
                "dateFrom": "2026-04-21",
                "dateTo": "2026-04-21",
                "rrDate": "2026-04-21",
                "orderDt": "2026-04-18T08:00:00Z",
                "saleDt": "2026-04-19T10:00:00Z",
                "nmId": 1001,
                "supplierArticle": "ART-1001",
                "quantity": 1,
                "retailAmount": 1800.0,
                "ppvzSalesCommission": 250.0,
                "deliveryAmount": -90.0,
                "paidStorage": -20.0,
                "acquiringFee": -15.0,
                "forPay": 1410.0,
                "docTypeName": "Продажа",
            },
            {
                "dateFrom": "2026-04-21",
                "dateTo": "2026-04-21",
                "rrDate": "2026-04-21",
                "saleDt": "2026-04-21T12:00:00Z",
                "quantity": 2,
                "docTypeName": "Возмещение издержек по перевозке/по складским операциям с товаром",
            },
        ]

        normalized = normalize_bundle(raw_bundle)
        finance_rows = normalized["finance_final_rows"]
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )

        self.assertEqual(finance_rows[0]["date"], "2026-04-21")
        self.assertEqual(finance_rows[0]["order_date"], "2026-04-18")
        self.assertEqual(finance_rows[0]["sale_date"], "2026-04-19")
        self.assertEqual(finance_rows[0]["row_group"], "sale")
        self.assertEqual(finance_rows[1]["row_group"], "reimbursement")
        self.assertEqual(finance_rows[1]["is_zero_technical"], True)
        self.assertEqual(reconciled["finance_final_daily"]["gross_revenue"], 1800.0)
        self.assertEqual(reconciled["finance_final_daily"]["seller_payout"], 1410.0)
        self.assertEqual(reconciled["finance_final_daily"]["logistics"], -90.0)
        self.assertEqual(reconciled["finance_final_daily"]["storage"], -20.0)
        self.assertEqual(reconciled["finance_final_daily"]["acquiring"], -15.0)
        self.assertEqual(reconciled["finance_final_daily"]["diagnostics"]["selected_rows_count"], 2)
        self.assertEqual(reconciled["finance_final_daily"]["diagnostics"]["effective_rows_count"], 1)
        self.assertEqual(reconciled["finance_final_daily"]["diagnostics"]["technical_zero_rows_count"], 1)

    def test_finance_non_zero_reimbursement_row_is_included_by_field(self) -> None:
        raw_bundle = _raw_bundle_fixture()
        raw_bundle["finance_final"]["rows_raw"] = [
            {
                "dateFrom": "2026-04-21",
                "dateTo": "2026-04-21",
                "rrDate": "2026-04-21",
                "saleDt": "2026-04-21T12:00:00Z",
                "quantity": 1,
                "deliveryAmount": -35.0,
                "forPay": -35.0,
                "docTypeName": "Возмещение издержек по перевозке/по складским операциям с товаром",
            }
        ]

        normalized = normalize_bundle(raw_bundle)
        finance_rows = normalized["finance_final_rows"]
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )

        self.assertEqual(finance_rows[0]["row_group"], "reimbursement")
        self.assertEqual(finance_rows[0]["include_in_totals"], True)
        self.assertEqual(finance_rows[0]["include_logistics"], True)
        self.assertEqual(finance_rows[0]["is_zero_technical"], False)
        self.assertEqual(reconciled["finance_final_daily"]["gross_revenue"], 0.0)
        self.assertEqual(reconciled["finance_final_daily"]["seller_payout"], -35.0)
        self.assertEqual(reconciled["finance_final_daily"]["logistics"], -35.0)

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
        self.assertEqual(reconciled["live_operational"]["stocks"]["snapshot_kind"], "live_snapshot")
        self.assertEqual(reconciled["live_operational"]["stocks"]["snapshot_date"], "2026-04-22")
        self.assertEqual(reconciled["live_operational"]["stocks"]["operational_date_reference"], "2026-04-21")
        self.assertEqual(reconciled["live_operational"]["stocks"]["total_units"], 22.0)
        self.assertTrue(all(str((row or {}).get("date") or "") == "2026-04-22" for row in stock_rows))
        warning_codes = {str(item.get("code") or "") for item in reconciled.get("warnings", []) if isinstance(item, dict)}
        self.assertNotIn("stocks_snapshot_date_misaligned", warning_codes)

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
        # Verify funnel_daily in snapshot (from test fixture without openCount/cartCount)
        self.assertEqual(snapshot["funnel_daily"]["open_count"], 0.0)
        self.assertEqual(snapshot["funnel_daily"]["cart_count"], 0.0)
        self.assertEqual(snapshot["funnel_daily"]["orders_count"], 5.0)
        self.assertEqual(snapshot["funnel_daily"]["buyouts_count"], 3.0)
        self.assertEqual(snapshot["funnel_daily"]["status"], "partial")
        self.assertIsNone(snapshot["funnel_daily"].get("rows"), "rows should not be in snapshot")
        self.assertEqual(snapshot["finance_final_daily"]["gross_revenue"], 1800.0)
        self.assertEqual(snapshot["live_operational"]["orders"]["count"], 1.0)
        self.assertEqual(snapshot["live_operational"]["stocks"]["snapshot_kind"], "live_snapshot")
        self.assertEqual(snapshot["live_operational"]["stocks"]["snapshot_date"], "2026-04-21")
        self.assertEqual(snapshot["live_operational"]["stocks"]["operational_date_reference"], "2026-04-21")
        self.assertIn("cabinet_commerce", debug["endpoints"])
        self.assertIn("finance_final", debug["endpoints"])
        self.assertEqual(debug["reconcile"]["selected_sources"]["cabinet_commerce_daily"], "sales_funnel_api")
        self.assertEqual(debug["counts"]["raw"]["cabinet_commerce"], 2)
        self.assertEqual(debug["reconcile"]["live_stocks_snapshot_date"], "2026-04-21")

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

    def test_cabinet_commerce_uses_fresh_local_cache_without_api_call(self) -> None:
        client = _FakeClient({})
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = os.path.join(
                temp_dir,
                "cabinets",
                "seller_001",
                "artifacts",
                "wb_api_core",
                "cache",
                "cabinet_commerce_daily",
            )
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, "2026-04-21.json")
            with open(cache_path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "seller_id": "seller_001",
                        "target_date": "2026-04-21",
                        "source_family": "cabinet_commerce_daily",
                        "cached_at_epoch": 4102444800.0,
                        "rows_raw": [
                            {
                                "product": {"nmId": 1001},
                                "statistic": {"selected": {"period": {"start": "2026-04-21", "end": "2026-04-21"}}},
                            }
                        ],
                        "debug": {"success": True},
                    },
                    file,
                    ensure_ascii=False,
                )

            with patch("wb_api_core.loaders.time.time", return_value=4102444800.0):
                bundle = load_cabinet_commerce(
                    client,
                    "2026-04-21",
                    seller_id="seller_001",
                    repo_root=temp_dir,
                )

        self.assertEqual(len(bundle["rows_raw"]), 1)
        self.assertEqual(len(client.calls), 0)
        self.assertEqual(bundle["debug"]["cache_hit"], True)
        self.assertEqual(bundle["debug"]["cache_mode"], "fresh_local_cache")
        self.assertEqual(bundle["debug"]["retry_count"], 0)

    def test_cabinet_commerce_falls_back_to_cache_after_retryable_failure(self) -> None:
        client = _AlwaysFailClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = os.path.join(
                temp_dir,
                "cabinets",
                "seller_001",
                "artifacts",
                "wb_api_core",
                "cache",
                "cabinet_commerce_daily",
            )
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, "2026-04-21.json")
            with open(cache_path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "seller_id": "seller_001",
                        "target_date": "2026-04-21",
                        "source_family": "cabinet_commerce_daily",
                        "cached_at_epoch": 4102444800.0 - 40000.0,
                        "rows_raw": [
                            {
                                "product": {"nmId": 1001},
                                "statistic": {"selected": {"period": {"start": "2026-04-21", "end": "2026-04-21"}}},
                            }
                        ],
                        "debug": {"success": True},
                    },
                    file,
                    ensure_ascii=False,
                )

            with patch("wb_api_core.loaders.time.time", return_value=4102444800.0):
                bundle = load_cabinet_commerce(
                    client,
                    "2026-04-21",
                    seller_id="seller_001",
                    repo_root=temp_dir,
                )

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(bundle["rows_raw"]), 1)
        self.assertEqual(bundle["debug"]["cache_hit"], True)
        self.assertEqual(bundle["debug"]["cache_fallback_used"], True)
        self.assertEqual(bundle["debug"]["cache_mode"], "failure_fallback")
        self.assertEqual(bundle["debug"]["retry_count"], 4)
        self.assertEqual(bundle["debug"]["retry_delays"], [3.0, 6.0, 12.0, 24.0])
        self.assertIn("429", bundle["debug"]["final_failure_reason"])
        self.assertEqual(bundle["debug"]["cache_path"], cache_path)

    def test_request_json_uses_retry_policy_metadata(self) -> None:
        client = WBApiClient(token="token")
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.text = "too many requests"
        rate_limited.headers = {}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"data": {"products": []}}
        success.text = ""
        success.headers = {}

        with patch("wb_api_core.client.requests.request", side_effect=[rate_limited, rate_limited, success]) as request_mock:
            with patch("wb_api_core.client.time.sleep") as sleep_mock:
                with patch("wb_api_core.client.random.uniform", return_value=0.0):
                    response = client.request_json(
                        endpoint_name="cabinet_commerce",
                        path="/api/analytics/v3/sales-funnel/products",
                        method="POST",
                        json_body={"selectedPeriod": {"start": "2026-04-21", "end": "2026-04-21"}},
                        base_url=client.analytics_base_url,
                        retry_policy={
                            "retryable_statuses": (429, 500, 502, 503, 504),
                            "max_attempts": 5,
                            "base_delay_seconds": 3.0,
                            "cap_delay_seconds": 45.0,
                            "jitter_ratio": 0.25,
                            "max_retry_window_seconds": 90.0,
                        },
                    )

        self.assertEqual(request_mock.call_count, 3)
        self.assertEqual(response["success"], True)
        self.assertEqual(response["attempts"], 3)
        self.assertEqual(response["retry_count"], 2)
        self.assertEqual(response["retry_delays"], [3.0, 6.0])
        self.assertEqual(response["final_failure_reason"], "")
        self.assertEqual(sleep_mock.call_count, 2)

    def test_funnel_daily_status_calculation(self) -> None:
        """Test funnel_daily status determination for various data scenarios."""
        raw_bundle = _raw_bundle_fixture()
        normalized = normalize_bundle(raw_bundle)
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )

        # Verify funnel_daily is created from cabinet_commerce_rows
        funnel = reconciled["funnel_daily"]
        self.assertEqual(funnel["source"], "sales_funnel_api")
        self.assertEqual(funnel["available"], True)
        
        # Verify all funnel stages are aggregated (test fixture has no open/cart data)
        self.assertEqual(funnel["open_count"], 0.0)
        self.assertEqual(funnel["cart_count"], 0.0)
        self.assertEqual(funnel["orders_count"], 5.0)
        self.assertEqual(funnel["buyouts_count"], 3.0)
        
        # Verify rates when denominator is 0 returns None
        self.assertIsNone(funnel["open_to_cart_rate"])
        self.assertIsNone(funnel["cart_to_order_rate"])
        self.assertAlmostEqual(funnel["order_to_buyout_rate"], 60.0, places=1)
        
        # Verify status fields - partial because only lower funnel available
        self.assertEqual(funnel["upper_funnel_status"], "unavailable")
        self.assertEqual(funnel["lower_funnel_status"], "ok")
        self.assertEqual(funnel["status"], "partial")

    def test_funnel_daily_no_rows_unavailable_status(self) -> None:
        """Test funnel_daily status when no cabinet_commerce data available."""
        raw_bundle = {
            "cabinet_commerce": {
                "success": False,
                "error_text": "API error",
                "rows_raw": [],
            },
            "finance_final": {"success": False, "error_text": "API error", "rows_raw": []},
            "orders": {"success": False, "error_text": "API error", "rows_raw": []},
            "sales": {"success": False, "error_text": "API error", "rows_raw": []},
            "stocks": {"success": False, "error_text": "API error", "rows_raw": []},
        }
        
        normalized = normalize_bundle(raw_bundle)
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )
        
        funnel = reconciled["funnel_daily"]
        self.assertEqual(funnel["available"], False)
        self.assertIsNone(funnel["open_count"])
        self.assertIsNone(funnel["cart_count"])
        self.assertEqual(funnel["status"], "unavailable")
        self.assertEqual(funnel["upper_funnel_status"], "unavailable")
        self.assertEqual(funnel["lower_funnel_status"], "unavailable")

    def test_funnel_daily_rates_null_when_zero_denominator(self) -> None:
        """Test that conversion rates are null when denominator is zero."""
        raw_bundle = {
            "cabinet_commerce": {
                "success": True,
                "error_text": "",
                "rows_raw": [
                    {
                        "product": {"nmId": 1001},
                        "statistic": {
                            "selected": {
                                "period": {"begin": "2026-04-21", "end": "2026-04-21"},
                                "openCardCount": 0,
                                "cartCount": 0,
                                "orderCount": 5,
                                "orderSum": 1000,
                                "buyoutCount": 0,
                                "buyoutSum": 0,
                            }
                        },
                    }
                ],
            },
            "finance_final": {"success": False, "error_text": "API error", "rows_raw": []},
            "orders": {"success": False, "error_text": "API error", "rows_raw": []},
            "sales": {"success": False, "error_text": "API error", "rows_raw": []},
            "stocks": {"success": False, "error_text": "API error", "rows_raw": []},
        }
        
        normalized = normalize_bundle(raw_bundle)
        reconciled = reconcile_bundle(
            raw_bundle=raw_bundle,
            normalized_bundle=normalized,
            target_date="2026-04-21",
        )
        
        funnel = reconciled["funnel_daily"]
        self.assertIsNone(funnel["open_to_cart_rate"], "Rate should be None when denominator is 0")
        self.assertIsNone(funnel["cart_to_order_rate"], "Rate should be None when denominator is 0")


if __name__ == "__main__":
    unittest.main()
