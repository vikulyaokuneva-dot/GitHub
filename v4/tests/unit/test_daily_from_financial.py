from __future__ import annotations

import unittest

from v4.core.contracts import DailyMetricsSection, FinancialMetricsSection, MetricStatus, MetricValue
from v4.metrics.daily.resolver import build_daily_metrics_from_financial


class TestDailyFromFinancial(unittest.TestCase):
    def test_daily_subset_mapping(self) -> None:
        metric = lambda value: MetricValue(value=value, status=MetricStatus.CONFIRMED.value, source="unit")
        financial = FinancialMetricsSection(
            orders_count=metric(10),
            sales_count=metric(7),
            returns_count=metric(2),
            orders_amount=metric(1234.0),
            sales_amount=metric(980.0),
            seller_payout=metric(700.0),
            logistics_cost=metric(50.0),
            storage_cost=metric(20.0),
            deductions_amount=metric(10.0),
            net_realization_amount=metric(900.0),
            realization_target_date="2026-03-15",
            realization_actual_date="2026-03-15",
            fallback_used=False,
            lag_days=0,
            source_quality={"orders": "ok", "sales": "ok", "realization": "ok"},
            warnings=[],
        )

        daily = build_daily_metrics_from_financial(financial)

        self.assertIsInstance(daily, DailyMetricsSection)
        self.assertEqual(daily.orders_count.value, 10)
        self.assertEqual(daily.sales_count.value, 7)
        self.assertEqual(daily.returns_count.value, 2)
        self.assertEqual(daily.orders_amount.value, 1234.0)
        self.assertEqual(daily.sales_amount.value, 980.0)


if __name__ == "__main__":
    unittest.main()
