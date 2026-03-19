from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    AdsMetricsSection,
    FinancialMetricsSection,
    FunnelMetricsSection,
    MetricValue,
    NormalizedBundle,
    NormalizedFunnelRecord,
    NormalizedStockRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
    StockMetricsSection,
)
from v4.metrics.health import assemble_health_metrics


def _metric(value, status: str = "confirmed", source: str | None = "test", note: str | None = None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


def _context() -> RunContext:
    d = date(2026, 3, 15)
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date=d,
        resolved_date=d,
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


def _status(name: str, code: SourceStatusCode, required: bool = False) -> SourceStatus:
    return SourceStatus(
        source_name=name,
        kind=SourceKind.API,
        status=code,
        is_required=required,
    )


def _normalized_bundle() -> NormalizedBundle:
    return NormalizedBundle(
        run_context=_context(),
        stocks=[
            NormalizedStockRecord("s1", None, 1001, "WH-A", "M", 120, "2026-03-15", "stocks", "raw-s1"),
            NormalizedStockRecord("s2", None, 1002, "WH-B", "M", 50, "2026-03-15", "stocks", "raw-s2"),
        ],
        funnel=[
            NormalizedFunnelRecord(1001, "2026-03-15", 200.0, 80.0, 30.0, 4.0, 2.0, "funnel", "raw-f1"),
            NormalizedFunnelRecord(1002, "2026-03-15", 200.0, 90.0, 40.0, 8.0, 4.0, "funnel", "raw-f2"),
        ],
        source_statuses={
            "sales": _status("sales", SourceStatusCode.OK, True),
            "realization": _status("realization", SourceStatusCode.OK, True),
            "funnel": _status("funnel", SourceStatusCode.OK, False),
            "ads_campaigns": _status("ads_campaigns", SourceStatusCode.OK, False),
            "ads_stats": _status("ads_stats", SourceStatusCode.OK, False),
            "stocks": _status("stocks", SourceStatusCode.OK, False),
        },
    )


def _financial_section(net_profit_like_value, status: str = "confirmed") -> FinancialMetricsSection:
    return FinancialMetricsSection(
        orders_count=_metric(10, source="orders"),
        sales_count=_metric(8, source="sales"),
        returns_count=_metric(2, source="sales"),
        orders_amount=_metric(1000.0, source="orders"),
        sales_amount=_metric(900.0, source="sales"),
        seller_payout=_metric(700.0, source="realization"),
        logistics_cost=_metric(50.0, source="realization"),
        storage_cost=_metric(10.0, source="realization"),
        deductions_amount=_metric(5.0, source="realization"),
        net_realization_amount=_metric(835.0, source="financial_formula"),
        gross_profit_like=_metric(net_profit_like_value, status=status, source="financial_formula"),
        net_profit_like=_metric(net_profit_like_value, status=status, source="financial_formula"),
    )


class TestHealthMetrics(unittest.TestCase):
    def test_health_score_is_deterministic(self) -> None:
        normalized = _normalized_bundle()
        financial = _financial_section(300.0, status="confirmed")
        ads = AdsMetricsSection(
            spend=_metric(100.0, source="ads"),
            revenue=_metric(260.0, source="ads"),
            conversion_click_to_order=_metric(0.04, source="ads"),
        )
        funnel = FunnelMetricsSection(
            orders=_metric(12.0, source="funnel"),
            buys=_metric(6.0, source="funnel"),
            cr_buys_from_orders=_metric(0.5, source="funnel"),
            cr_buys_from_impressions=_metric(0.03, source="funnel"),
        )
        stock = StockMetricsSection(
            in_stock_items_count=_metric(19, source="stocks"),
            out_of_stock_items_count=_metric(1, source="stocks"),
        )

        first = assemble_health_metrics(
            normalized_bundle=normalized,
            financial=financial,
            funnel=funnel,
            ads=ads,
            stock=stock,
        )
        second = assemble_health_metrics(
            normalized_bundle=normalized,
            financial=financial,
            funnel=funnel,
            ads=ads,
            stock=stock,
        )

        self.assertEqual(first.business_health_score.value, second.business_health_score.value)
        self.assertEqual(first.business_health_score.status, "confirmed")
        self.assertGreaterEqual(float(first.business_health_score.value or 0.0), 0.0)
        self.assertLessEqual(float(first.business_health_score.value or 0.0), 100.0)

    def test_none_is_not_forced_to_zero(self) -> None:
        normalized = _normalized_bundle()
        financial = _financial_section(None, status="partial")
        ads = AdsMetricsSection(
            spend=_metric(None, status="partial", source="ads"),
            revenue=_metric(None, status="partial", source="ads"),
            conversion_click_to_order=_metric(None, status="partial", source="ads"),
        )

        health = assemble_health_metrics(
            normalized_bundle=normalized,
            financial=financial,
            funnel=None,
            ads=ads,
            stock=None,
        )

        profitability = health.component_scores["profitability"]
        self.assertIsNone(profitability.value)
        self.assertNotEqual(profitability.value, 0)
        self.assertIsNone(health.business_health_score.value)
        self.assertEqual(health.business_health_score.status, "unavailable")

    def test_partial_inputs_produce_partial_health_status(self) -> None:
        normalized = _normalized_bundle()
        normalized.source_statuses["ads_campaigns"] = _status("ads_campaigns", SourceStatusCode.MISSING, False)
        normalized.source_statuses["ads_stats"] = _status("ads_stats", SourceStatusCode.MISSING, False)

        financial = _financial_section(40.0, status="confirmed")
        funnel = FunnelMetricsSection(
            cr_buys_from_orders=_metric(0.2, status="partial", source="funnel"),
            cr_buys_from_impressions=_metric(None, status="partial", source="funnel"),
        )
        stock = StockMetricsSection(
            in_stock_items_count=_metric(5, source="stocks"),
            out_of_stock_items_count=_metric(1, source="stocks"),
        )

        health = assemble_health_metrics(
            normalized_bundle=normalized,
            financial=financial,
            funnel=funnel,
            ads=None,
            stock=stock,
        )

        self.assertEqual(health.business_health_score.status, "partial")
        self.assertIsNotNone(health.business_health_status_note)
        assert health.business_health_status_note is not None
        self.assertIn("partial", health.business_health_status_note)


if __name__ == "__main__":
    unittest.main()

