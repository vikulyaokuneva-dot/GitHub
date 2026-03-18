from __future__ import annotations

import unittest

from v4.core.contracts import (
    AdsMetricsSection,
    DailyMetricsSection,
    FinancialMetricsSection,
    FunnelMetricsSection,
    MetricValue,
    MetricsBundle,
    RunContext,
    RunMode,
    StockMetricsSection,
)
from v4.outputs.facts.builder import build_facts_bundle
from v4.pipeline.stages.facts_stage import run as run_facts_stage


def _metric(value, status="confirmed", source=None, note=None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


class TestFactsBundleBuild(unittest.TestCase):
    def test_build_facts_bundle_propagates_quality_and_diagnostics(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

        financial = FinancialMetricsSection(
            orders_count=_metric(10, source="orders"),
            sales_count=_metric(8, source="sales"),
            returns_count=_metric(2, source="sales"),
            orders_amount=_metric(1000.0, source="orders"),
            sales_amount=_metric(900.0, source="sales"),
            seller_payout=_metric(700.0, status="partial", source="realization"),
            logistics_cost=_metric(50.0, source="realization"),
            storage_cost=_metric(10.0, source="realization"),
            deductions_amount=_metric(5.0, source="realization"),
            net_realization_amount=_metric(None, status="partial", source="realization"),
            source_quality={"orders": "ok", "sales": "ok", "realization": "partial"},
            component_quality={"revenue": "ok"},
            warnings=["realization partial"],
        )
        daily = DailyMetricsSection(
            orders_count=_metric(10, source="orders"),
            sales_count=_metric(8, source="sales"),
            returns_count=_metric(2, source="sales"),
            orders_amount=_metric(1000.0, source="orders"),
            sales_amount=_metric(900.0, source="sales"),
        )
        funnel = FunnelMetricsSection(
            impressions=_metric(1000.0, source="funnel"),
            opens=_metric(500.0, source="funnel"),
            cart_adds=_metric(200.0, source="funnel"),
            orders=_metric(100.0, source="funnel"),
            buys=_metric(80.0, source="funnel"),
            ctr_open_from_impressions=_metric(0.5, source="funnel"),
            cr_cart_from_opens=_metric(0.4, source="funnel"),
            cr_orders_from_cart=_metric(0.5, source="funnel"),
            cr_buys_from_orders=_metric(0.8, source="funnel"),
            cr_buys_from_impressions=_metric(0.08, source="funnel"),
            source_quality={"funnel": "ok"},
            warnings=[],
        )
        ads = AdsMetricsSection(
            campaigns_count=_metric(5, source="ads_campaigns"),
            active_campaigns_count=_metric(3, source="ads_campaigns"),
            impressions=_metric(5000.0, source="ads_stats"),
            clicks=_metric(250.0, source="ads_stats"),
            spend=_metric(1200.0, source="ads_stats"),
            ctr=_metric(0.05, source="ads_stats"),
            cpc=_metric(4.8, source="ads_stats"),
            orders=_metric(None, status="partial", source="ads_stats"),
            revenue=_metric(None, status="unavailable", source="ads_stats"),
            conversion_click_to_order=_metric(None, status="partial", source="ads_stats"),
            source_quality={"campaigns": "ok", "stats": "partial"},
            warnings=["ads stats partial"],
        )
        stock = StockMetricsSection(
            total_stock_units=_metric(100.0, status="partial", source="stocks"),
            in_stock_items_count=_metric(12, source="stocks"),
            out_of_stock_items_count=_metric(3, source="stocks"),
            distinct_nm_ids_count=_metric(10, source="stocks"),
            distinct_warehouses_count=_metric(2, source="stocks"),
            source_quality={"stocks": "partial"},
            warnings=["stock quantities partially missing"],
        )

        metrics = MetricsBundle(
            run_context=context,
            financial=financial,
            daily=daily,
            funnel=funnel,
            ads=ads,
            stock=stock,
            warnings=["metrics warning"],
            diagnostics={"metrics_sections_built": ["financial", "daily", "funnel", "ads", "stock"]},
            source_flags={"orders": "ok", "sales": "ok", "realization": "partial"},
        )

        facts = build_facts_bundle(metrics)

        self.assertEqual(set(facts.sections.keys()), {"financial", "daily", "funnel", "ads", "stock"})
        self.assertIn("financial", facts.data_quality["available_sections"])
        self.assertIn("metrics_sections_built", facts.diagnostics)
        self.assertIn("facts_sections_built", facts.diagnostics)
        self.assertIn("warnings_count", facts.data_quality)
        self.assertIn("metrics warning", facts.warnings)

        from_stage = run_facts_stage(metrics)
        self.assertEqual(set(from_stage.sections.keys()), set(facts.sections.keys()))


if __name__ == "__main__":
    unittest.main()
