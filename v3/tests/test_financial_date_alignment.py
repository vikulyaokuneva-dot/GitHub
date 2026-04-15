import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from v3.outputs.daily_email_stage import run_daily_email_stage
from v3.pipeline.daily_metrics_stage import run_daily_metrics_stage


def _base_ctx(*, actual_financial_date: str, fallback_used: bool) -> Dict[str, Any]:
    return {
        "repo_root": "",
        "seller_id": "seller_financial_alignment",
        "run_date": "2026-04-15",
        "seller_name": "Seller Financial Alignment",
        "token": "token",
        "source_mode": "wb_api",
        "cfg": {
            "tax_rate": 0.06,
            "territorial_distribution": {
                "min_portfolio_coverage_pct": 0.0,
                "min_demand_coverage_pct": 0.0,
                "min_stock_coverage_pct": 0.0,
                "max_unknown_share_pct": 100.0,
            },
        },
        "sales_rows": [
            {
                "date": f"{actual_financial_date}T09:00:00",
                "sku": "1001",
                "seller_sku": "SKU-1001",
                "revenue": 900.0,
                "profit": 140.0,
                "orders": 1.0,
                "buys": 1.0,
                "sales_count": 1.0,
                "cost_price": 600.0,
                "wb_commission": 100.0,
                "logistics": 40.0,
                "penalties": 0.0,
                "storage": 20.0,
                "deductions": 0.0,
            }
        ],
        "ads_rows": [],
        "stocks_rows": [{"sku": "1001", "nm_id": "1001", "stock": 10, "warehouse": "Moscow WH"}],
        "api_orders_rows": [
            {"date": "2026-04-14T10:00:00", "nmId": 1001, "srid": "order-1", "totalPrice": 1000.0}
        ],
        "api_sales_rows": [
            {"date": "2026-04-14T11:00:00", "nmId": 1001, "saleID": "sale-1", "priceWithDisc": 900.0}
        ],
        "api_realization_rows": [
            {"date": f"{actual_financial_date}T12:00:00", "nmId": 1001, "retail_price_withdisc_rub": 900.0}
        ],
        "api_stocks_rows": [{"sku": "1001", "nm_id": "1001", "stock": 10, "warehouse": "Moscow WH"}],
        "supplier_goods_daily": {},
        "discovered_files": {},
        "input_debug": {},
        "api_debug": {
            "orders_rows": 1,
            "sales_rows": 1,
            "realization_rows": 1,
            "financial_rows": 1,
            "date_from": "2026-04-14",
            "run_date_requested": "2026-04-15",
            "realization_target_date": "2026-04-14",
            "realization_actual_source_date": actual_financial_date,
            "realization_fallback_used": bool(fallback_used),
            "realization_fallback_lag_days": 2 if fallback_used else 0,
        },
        "event_date_model": {
            "report_date": "2026-04-15",
            "operational_date": "2026-04-14",
            "orders_date": "2026-04-14",
            "buyouts_date": "2026-04-14",
            "financial_date": actual_financial_date,
        },
    }


class TestFinancialDateAlignment(unittest.TestCase):
    def _run_metrics(self, *, actual_financial_date: str, fallback_used: bool) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = str(Path(tmp_dir) / "out")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ctx = _base_ctx(actual_financial_date=actual_financial_date, fallback_used=fallback_used)
            ctx["out_dir"] = out_dir
            return run_daily_metrics_stage(ctx)

    def test_financials_marked_misaligned_when_realization_actual_date_differs(self) -> None:
        ctx = self._run_metrics(actual_financial_date="2026-04-12", fallback_used=True)
        financial_kpi = ctx.get("financial_kpi", {})
        status_matrix = ctx.get("daily_status_matrix", {})

        self.assertFalse(bool(financial_kpi.get("financial_date_aligned", True)))
        self.assertEqual(str(financial_kpi.get("financial_alignment_status") or ""), "lagged_fallback")
        self.assertEqual(str(financial_kpi.get("financial_actual_date") or ""), "2026-04-12")
        self.assertEqual(str(financial_kpi.get("financial_target_date") or ""), "2026-04-14")
        self.assertNotEqual(str(status_matrix.get("financials") or ""), "confirmed")

    def test_financials_aligned_when_actual_date_matches_operational_date(self) -> None:
        ctx = self._run_metrics(actual_financial_date="2026-04-14", fallback_used=False)
        financial_kpi = ctx.get("financial_kpi", {})

        self.assertTrue(bool(financial_kpi.get("financial_date_aligned", False)))
        self.assertEqual(str(financial_kpi.get("financial_alignment_status") or ""), "aligned")
        self.assertEqual(str(financial_kpi.get("financial_actual_date") or ""), "2026-04-14")
        self.assertEqual(str(financial_kpi.get("financial_target_date") or ""), "2026-04-14")

    def test_orders_buyouts_remain_confirmed_even_when_financials_lagged(self) -> None:
        ctx = self._run_metrics(actual_financial_date="2026-04-12", fallback_used=True)
        daily_kpi = ctx.get("daily_kpi", {})
        financial_kpi = ctx.get("financial_kpi", {})

        self.assertTrue(bool(daily_kpi.get("orders_count_confirmed", False)))
        self.assertTrue(bool(daily_kpi.get("buyouts_count_confirmed", False)))
        self.assertEqual(int(daily_kpi.get("daily_orders_count", 0) or 0), 1)
        self.assertEqual(int(daily_kpi.get("daily_buyouts_count", 0) or 0), 1)
        self.assertEqual(str(financial_kpi.get("financial_alignment_status") or ""), "lagged_fallback")
        self.assertFalse(bool(financial_kpi.get("financial_date_aligned", True)))

    def test_email_summary_mentions_financial_lag(self) -> None:
        ctx = self._run_metrics(actual_financial_date="2026-04-12", fallback_used=True)
        out = run_daily_email_stage(ctx)
        summary = out.get("job", {}).get("email_summary", {})
        key_insights = summary.get("key_insights", []) if isinstance(summary.get("key_insights"), list) else []
        joined = "\n".join(str(item).lower() for item in key_insights)

        self.assertIn("финансовые данные wb доступны только за 2026-04-12", joined)
        self.assertIn("заказы и выкупы подтверждены за 2026-04-14", joined)


if __name__ == "__main__":
    unittest.main()
