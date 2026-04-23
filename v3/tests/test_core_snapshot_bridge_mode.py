import json
import os
import tempfile
import unittest
from unittest.mock import patch

from v3.core_report_bridge import CoreSnapshotBridgeFatalError
from v3.outputs.daily_artifacts_stage import prepare_daily_output_payload
from v3.outputs.daily_email_stage import run_daily_email_stage
from v3.outputs.daily_report_stage import run_daily_report_stage


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _snapshot_payload() -> dict:
    return {
        "seller_id": "seller_001",
        "run_date": "2026-04-23",
        "operational_date": "2026-04-22",
        "timezone": "Europe/Moscow",
        "source_mode": "wb_api_core_v2",
        "cabinet_commerce_daily": {
            "source": "sales_funnel_api",
            "available": True,
            "target_date": "2026-04-22",
            "orders_count": 5,
            "orders_amount": 4260.0,
            "buyouts_count": 2,
            "buyouts_amount": 1700.0,
        },
        "finance_final_daily": {
            "source": "finance_detailed_api",
            "available": True,
            "target_date": "2026-04-22",
            "actual_date": "2026-04-22",
            "date_aligned": True,
            "gross_revenue": 4652.0,
            "seller_payout": 4868.22,
            "wb_commission": -329.75,
            "logistics": 3.0,
            "storage": 68.37,
            "penalties": 0.0,
            "deductions": 0.0,
            "acquiring": 186.08,
            "tax": 0.0,
        },
        "live_operational": {
            "orders": {
                "source": "orders_api",
                "available": True,
                "target_date": "2026-04-22",
                "count": 3,
                "amount": 2500.0,
            },
            "sales": {
                "source": "sales_api",
                "available": True,
                "target_date": "2026-04-22",
                "count": 3,
                "amount": 7160.0,
            },
            "stocks": {
                "source": "stocks_api",
                "available": True,
                "snapshot_kind": "live_snapshot",
                "operational_date_reference": "2026-04-22",
                "snapshot_date": "2026-04-23",
                "total_units": 123,
            },
        },
    }


def _debug_payload() -> dict:
    return {
        "seller_id": "seller_001",
        "run_date": "2026-04-23",
        "operational_date": "2026-04-22",
        "timezone": "Europe/Moscow",
        "source_mode": "wb_api_core_v2",
        "endpoints": {
            "cabinet_commerce": {
                "success": True,
                "status_code": 200,
                "attempts": 1,
                "rows_loaded": 22,
                "error_text": "",
                "base_url": "https://seller-analytics-api.wildberries.ru",
                "cache_hit": False,
                "retry_count": 1,
                "retry_delays": [1.0],
                "final_failure_reason": "",
                "pages_loaded": 1,
                "page_limit": 100,
                "cache_mode": "",
                "cache_path": "",
                "cache_age_seconds": None,
                "cache_fallback_used": False,
            },
            "finance_final": {
                "success": True,
                "status_code": 200,
                "attempts": 1,
                "rows_loaded": 20,
                "error_text": "",
                "base_url": "https://finance-api.wildberries.ru",
                "cache_hit": False,
                "retry_count": 0,
                "retry_delays": [],
                "final_failure_reason": "",
                "finance_endpoint_used": "/api/finance/v1/sales-reports/detailed",
                "finance_requested_fields_count": 0,
                "finance_payload_incompatible": False,
            },
            "orders": {
                "success": True,
                "status_code": 200,
                "attempts": 1,
                "rows_loaded": 3,
                "error_text": "",
                "base_url": "https://statistics-api.wildberries.ru",
                "cache_hit": False,
                "retry_count": 0,
                "retry_delays": [],
                "final_failure_reason": "",
            },
            "sales": {
                "success": True,
                "status_code": 200,
                "attempts": 1,
                "rows_loaded": 3,
                "error_text": "",
                "base_url": "https://statistics-api.wildberries.ru",
                "cache_hit": False,
                "retry_count": 0,
                "retry_delays": [],
                "final_failure_reason": "",
            },
            "stocks": {
                "success": True,
                "status_code": 200,
                "attempts": 1,
                "rows_loaded": 5,
                "error_text": "",
                "base_url": "https://statistics-api.wildberries.ru",
                "cache_hit": False,
                "retry_count": 0,
                "retry_delays": [],
                "final_failure_reason": "",
            },
        },
        "warnings": [],
    }


class TestCoreSnapshotBridgeMode(unittest.TestCase):
    def _make_repo_with_snapshot(self, *, with_debug: bool = True) -> str:
        tmp_dir = tempfile.mkdtemp()
        artifacts_dir = os.path.join(
            tmp_dir,
            "cabinets",
            "seller_001",
            "artifacts",
            "wb_api_core",
            "2026-04-23",
        )
        _write_json(os.path.join(artifacts_dir, "snapshot.json"), _snapshot_payload())
        if with_debug:
            _write_json(os.path.join(artifacts_dir, "debug.json"), _debug_payload())
        return tmp_dir

    def test_core_snapshot_mode_uses_bridge_and_mirrors_core_values(self) -> None:
        repo_root = self._make_repo_with_snapshot(with_debug=True)
        with patch.dict(os.environ, {"PDF_SOURCE_MODE": "core_snapshot"}, clear=False):
            with patch(
                "v3.outputs.daily_artifacts_stage.build_core_report_payload",
                wraps=prepare_daily_output_payload.__globals__["build_core_report_payload"],
            ) as build_mock:
                payload = prepare_daily_output_payload(
                    {
                        "repo_root": repo_root,
                        "seller_id": "seller_001",
                        "run_date": "2026-04-23",
                        "out_dir": "",
                    }
                )

        self.assertTrue(build_mock.called)
        self.assertEqual(payload.get("source_mode"), "core_snapshot")
        self.assertEqual(payload.get("pdf_source_mode"), "core_snapshot")
        self.assertIn("core_report_payload", payload)
        self.assertEqual(payload.get("daily_orders_count"), 5)
        self.assertEqual(payload.get("daily_orders_amount"), 4260.0)
        self.assertEqual(payload.get("daily_buyouts_count"), 2)
        self.assertEqual(payload.get("daily_buyouts_amount"), 1700.0)
        self.assertEqual(payload.get("render_kpi", {}).get("orders_count"), 5)
        self.assertEqual(payload.get("render_kpi", {}).get("buyouts_count"), 2)
        self.assertEqual(payload.get("render_kpi", {}).get("buyouts_amount"), 1700.0)
        self.assertEqual(payload.get("financial_kpi", {}).get("seller_payout"), 4868.22)
        self.assertIsNone(payload.get("daily_orders_count_legacy"))
        self.assertIsNone(payload.get("revenue_total_legacy"))
        self.assertTrue(payload.get("source_flags", {}).get("debug_present"))

    def test_core_snapshot_stages_ignore_stale_legacy_fields(self) -> None:
        repo_root = self._make_repo_with_snapshot(with_debug=True)
        with tempfile.TemporaryDirectory() as out_dir:
            with patch.dict(os.environ, {"PDF_SOURCE_MODE": "core_snapshot"}, clear=False):
                payload = prepare_daily_output_payload(
                    {
                        "repo_root": repo_root,
                        "seller_id": "seller_001",
                        "run_date": "2026-04-23",
                        "out_dir": out_dir,
                    }
                )

            payload.update(
                {
                    "daily_orders_count": 4,
                    "daily_orders_amount": 8000.0,
                    "daily_buyouts_count": 3,
                    "daily_buyouts_amount": 9000.0,
                    "avg_check": 3000.0,
                    "seller_payout_total": 111.0,
                    "revenue_total": 222.0,
                    "wb_commission": 999.0,
                    "logistics_total": 777.0,
                    "storage_total": 555.0,
                    "render_kpi": {
                        "orders_count": 4,
                        "orders_amount": 8000.0,
                        "buyouts_count": 3,
                        "buyouts_amount": 9000.0,
                        "avg_check": 3000.0,
                        "revenue": 222.0,
                        "net_profit": 444.0,
                        "margin_pct": 55.0,
                    },
                    "daily_kpi": {
                        "daily_orders_count": 4,
                        "daily_orders_amount": 8000.0,
                        "daily_buyouts_count": 3,
                        "daily_buyouts_amount": 9000.0,
                        "orders_count_confirmed": True,
                        "buyouts_count_confirmed": True,
                    },
                    "financial_kpi": {
                        "seller_payout": 222.0,
                        "gross_revenue": 333.0,
                        "wb_commission": 999.0,
                        "logistics": 777.0,
                        "storage": 555.0,
                        "net_profit": 444.0,
                        "margin_pct": 55.0,
                    },
                }
            )

            email_ctx = run_daily_email_stage(dict(payload))
            summary = (
                email_ctx.get("job", {}).get("email_summary", {})
                if isinstance(email_ctx.get("job"), dict)
                else {}
            )
            self.assertEqual(summary.get("daily_orders_count"), 5)
            self.assertEqual(summary.get("daily_orders_amount"), 4260.0)
            self.assertEqual(summary.get("daily_buyouts_count"), 2)
            self.assertEqual(summary.get("daily_buyouts_amount"), 1700.0)
            self.assertEqual(summary.get("financial_revenue"), 4868.22)
            self.assertEqual(summary.get("avg_check"), 850.0)

            try:
                report_ctx = run_daily_report_stage(email_ctx)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            report_meta = report_ctx.get("report_meta", {})
            self.assertEqual(report_meta.get("source_mode"), "core_snapshot")
            self.assertEqual(report_meta.get("pdf_source_mode"), "core_snapshot")
            self.assertTrue(report_meta.get("core_report_payload_available"))
            self.assertEqual(report_meta.get("daily_commerce_kpi", {}).get("daily_orders_count"), 5)
            self.assertEqual(report_meta.get("daily_commerce_kpi", {}).get("daily_orders_amount"), 4260.0)
            self.assertEqual(report_meta.get("daily_commerce_kpi", {}).get("daily_buyouts_count"), 2)
            self.assertEqual(report_meta.get("daily_commerce_kpi", {}).get("daily_buyouts_amount"), 1700.0)
            self.assertEqual(report_meta.get("daily_financial_kpi", {}).get("seller_payout"), 4868.22)
            self.assertEqual(report_meta.get("daily_financial_kpi", {}).get("wb_commission"), -329.75)
            self.assertEqual(report_meta.get("daily_financial_kpi", {}).get("logistics"), 3.0)
            self.assertEqual(report_meta.get("daily_financial_kpi", {}).get("storage"), 68.37)
            self.assertIsNone(report_meta.get("daily_financial_kpi", {}).get("net_profit"))
            self.assertEqual(
                report_ctx.get("visual_payload", {}).get("live_operational", {}).get("orders", {}).get("count"),
                3,
            )
            self.assertEqual(
                report_ctx.get("visual_payload", {}).get("live_operational", {}).get("sales", {}).get("amount"),
                7160.0,
            )

    def test_core_snapshot_mode_without_snapshot_fails_without_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            with patch.dict(os.environ, {"PDF_SOURCE_MODE": "core_snapshot"}, clear=False):
                with self.assertRaises(CoreSnapshotBridgeFatalError):
                    prepare_daily_output_payload(
                        {
                            "repo_root": repo_root,
                            "seller_id": "seller_001",
                            "run_date": "2026-04-23",
                            "daily_kpi": {"daily_orders_count": 999},
                            "render_kpi": {"orders_count": 999},
                        }
                    )

    def test_core_snapshot_mode_without_debug_builds_with_warning(self) -> None:
        repo_root = self._make_repo_with_snapshot(with_debug=False)
        with patch.dict(os.environ, {"PDF_SOURCE_MODE": "core_snapshot"}, clear=False):
            payload = prepare_daily_output_payload(
                {
                    "repo_root": repo_root,
                    "seller_id": "seller_001",
                    "run_date": "2026-04-23",
                    "out_dir": "",
                }
            )

        self.assertEqual(payload.get("source_mode"), "core_snapshot")
        self.assertFalse(payload.get("core_report_payload", {}).get("source_flags", {}).get("debug_present"))
        warnings_collector = payload.get("warnings_collector")
        warnings = warnings_collector.export_warnings() if hasattr(warnings_collector, "export_warnings") else []
        self.assertTrue(any(str(item.get("code")) == "core_debug_missing" for item in warnings if isinstance(item, dict)))

    def test_legacy_mode_keeps_previous_prepare_flow(self) -> None:
        with patch.dict(os.environ, {"PDF_SOURCE_MODE": "legacy"}, clear=False):
            payload = prepare_daily_output_payload(
                {
                    "out_dir": "",
                    "analytics": {
                        "profit_contribution": {
                            "status": "ok",
                            "summary": {"sku_count": 1},
                            "items": [{"sku": "SKU1", "profit": 10.0, "profit_group": "P1"}],
                        }
                    },
                }
            )

        self.assertEqual(payload.get("pdf_source_mode"), "legacy")
        self.assertNotIn("core_report_payload", payload)
        self.assertEqual(payload.get("profit_contribution", {}).get("status"), "ok")
        self.assertEqual(payload.get("analytics", {}).get("profit_contribution", {}).get("summary", {}).get("sku_count"), 1)

    def test_core_snapshot_stages_require_core_report_payload(self) -> None:
        with self.assertRaises(ValueError):
            run_daily_email_stage({"source_mode": "core_snapshot"})
        with self.assertRaises(ValueError):
            run_daily_report_stage({"source_mode": "core_snapshot"})


if __name__ == "__main__":
    unittest.main()
