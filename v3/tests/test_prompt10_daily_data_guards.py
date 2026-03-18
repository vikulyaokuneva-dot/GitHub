from __future__ import annotations

import unittest
from unittest.mock import patch

from v3.metrics.sales_funnel_assembler import assemble_sales_funnel
from v3.outputs.email_summary_builder import build_email_summary
from v3.sources import wb_reports_loader as loader


class TestPrompt10DailyPipelineGuards(unittest.TestCase):
    def test_parser_separates_sales_and_logistics_rows(self) -> None:
        sales_reason = loader._DAILY_PAYMENT_REASON_TOKENS["sales_rows"][0]
        logistics_reason = loader._DAILY_PAYMENT_REASON_TOKENS["logistics_rows"][0]
        pvz_reason = loader._DAILY_PAYMENT_REASON_TOKENS["pvz_rows"][0]
        storage_reason = loader._DAILY_PAYMENT_REASON_TOKENS["storage_rows"][0]
        deductions_reason = loader._DAILY_PAYMENT_REASON_TOKENS["deductions_rows"][0]

        rows = [
            {"payment_reason": sales_reason, "qty": 2},
            {"payment_reason": logistics_reason, "qty": 5},
            {"payment_reason": pvz_reason, "qty": 1},
            {"payment_reason": storage_reason, "qty": 1},
            {"payment_reason": deductions_reason, "qty": 1},
        ]

        grouped = loader._split_daily_detailed_rows_by_reason(rows, "payment_reason")

        self.assertEqual(len(grouped.get("sales_rows", [])), 1)
        self.assertEqual(len(grouped.get("logistics_rows", [])), 1)
        self.assertEqual(len(grouped.get("pvz_rows", [])), 1)
        self.assertEqual(len(grouped.get("storage_rows", [])), 1)
        self.assertEqual(len(grouped.get("deductions_rows", [])), 1)

    def test_funnel_xlsx_is_extracted(self) -> None:
        columns = [
            "\u0410\u0440\u0442\u0438\u043a\u0443\u043b WB",
            "\u041f\u043e\u043a\u0430\u0437\u044b",
            "\u041f\u043e\u043b\u043e\u0436\u0438\u043b\u0438 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443",
            "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438, \u0448\u0442",
            "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438, \u0448\u0442",
            "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438 \u043d\u0430 \u0441\u0443\u043c\u043c\u0443, \u20bd",
            "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438 \u043d\u0430 \u0441\u0443\u043c\u043c\u0443, \u20bd",
        ]
        records = [
            {
                "\u0410\u0440\u0442\u0438\u043a\u0443\u043b WB": "1001",
                "\u041f\u043e\u043a\u0430\u0437\u044b": 100,
                "\u041f\u043e\u043b\u043e\u0436\u0438\u043b\u0438 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443": 10,
                "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438, \u0448\u0442": 5,
                "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438, \u0448\u0442": 4,
                "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438 \u043d\u0430 \u0441\u0443\u043c\u043c\u0443, \u20bd": 1000,
                "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438 \u043d\u0430 \u0441\u0443\u043c\u043c\u0443, \u20bd": 900,
            },
            {
                "\u0410\u0440\u0442\u0438\u043a\u0443\u043b WB": "",
                "\u041f\u043e\u043a\u0430\u0437\u044b": 999,
                "\u041f\u043e\u043b\u043e\u0436\u0438\u043b\u0438 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443": 999,
                "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438, \u0448\u0442": 999,
                "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438, \u0448\u0442": 999,
            },
            {
                "\u0410\u0440\u0442\u0438\u043a\u0443\u043b WB": "1002",
                "\u041f\u043e\u043a\u0430\u0437\u044b": 200,
                "\u041f\u043e\u043b\u043e\u0436\u0438\u043b\u0438 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443": 20,
                "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438, \u0448\u0442": 8,
                "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438, \u0448\u0442": 7,
                "\u0417\u0430\u043a\u0430\u0437\u0430\u043b\u0438 \u043d\u0430 \u0441\u0443\u043c\u043c\u0443, \u20bd": 1600,
                "\u0412\u044b\u043a\u0443\u043f\u0438\u043b\u0438 \u043d\u0430 \u0441\u0443\u043c\u043c\u0443, \u20bd": 1400,
            },
        ]

        with patch.object(loader, "pd", None), patch.object(loader, "_read_table", return_value=(columns, records)):
            payload = loader.parse_funnel_report_xlsx("dummy.xlsx")

        totals = payload.get("cabinet_totals", {})
        sku_rows = payload.get("sku_rows", [])

        self.assertEqual(len(sku_rows), 2)
        self.assertEqual(totals.get("views"), 300.0)
        self.assertEqual(totals.get("add_to_cart"), 30.0)
        self.assertEqual(totals.get("orders"), 13.0)
        self.assertEqual(totals.get("buyouts"), 11.0)
        self.assertEqual(totals.get("orders_amount"), 2600.0)
        self.assertEqual(totals.get("buyouts_amount"), 2300.0)

    def test_conversion_over_100_is_not_counted(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-03-16",
            metrics={
                "totals": {"views": 1000, "orders": 6, "buys": 7},
                "data_sources": {
                    "orders_count": "api.orders",
                    "buyouts_count": "api.sales",
                    "ads_spend": "unknown",
                },
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        self.assertIsNone(funnel.get("buyout_rate"))
        self.assertIsNone(funnel.get("order_to_buyout_conversion_pct"))
        self.assertTrue(bool(funnel.get("order_to_buyout_over_100")))
        self.assertTrue(bool(str(funnel.get("order_to_buyout_note") or "").strip()))

    def test_none_values_are_not_replaced_with_zero(self) -> None:
        summary = build_email_summary(
            daily_kpi={},
            ads_summary={},
            net_profit=None,
            gross_profit=None,
            cost_price=None,
            wb_commission=None,
            logistics=None,
            storage=None,
            penalties=None,
            deductions=None,
            ads_spend_total=None,
            margin_pct=None,
            profitability_pct=None,
            financial_completeness_pct=None,
            financial_partial=True,
            ads_rows=None,
            ads_impressions=None,
            ads_clicks=None,
            ads_orders=None,
            ads_loaded_from_file=False,
            ads_source_file="",
            ads_attribution_quality="missing_ads_data",
            daily_revenue=None,
            financial_revenue=None,
            daily_orders_count=None,
            avg_check=None,
            daily_orders_amount=None,
            daily_buyouts_count=None,
            daily_buyouts_amount=None,
            key_insights=[],
            recommendations=[],
            ai_day_conclusion="",
            event_date_model={},
            order_kpi={},
            buyout_kpi={},
            financial_kpi={},
            daily_status_matrix={},
            render_kpi={},
        )

        self.assertIsNone(summary.get("financial_completeness_pct"))
        self.assertIsNone(summary.get("ads_rows"))
        self.assertIsNone(summary.get("ads_impressions"))
        self.assertIsNone(summary.get("ads_clicks"))
        self.assertIsNone(summary.get("ads_orders"))
        self.assertIsNone(summary.get("net_profit"))

        display = summary.get("display", {})
        no_data = "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445"
        self.assertEqual(display.get("orders_count"), no_data)
        self.assertEqual(display.get("orders_amount"), no_data)
        self.assertEqual(display.get("buyouts_count"), no_data)
        self.assertEqual(display.get("buyouts_amount"), no_data)
        self.assertEqual(display.get("avg_check"), no_data)
        self.assertEqual(display.get("financial_revenue"), no_data)
        self.assertEqual(display.get("net_profit"), no_data)
        self.assertEqual(display.get("margin_pct"), no_data)
        self.assertEqual(display.get("profitability_pct"), no_data)


if __name__ == "__main__":
    unittest.main()
