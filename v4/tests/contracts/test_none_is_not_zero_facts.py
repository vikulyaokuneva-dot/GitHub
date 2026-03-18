from __future__ import annotations

import unittest

from v4.core.contracts import FinancialMetricsSection, MetricValue, MetricsBundle, RunContext, RunMode
from v4.outputs.facts.builder import build_facts_bundle


class TestNoneIsNotZeroFacts(unittest.TestCase):
    def test_none_metrics_remain_none_in_facts(self) -> None:
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
            orders_count=MetricValue(value=None, status="unavailable", source="orders", note="missing"),
            sales_count=MetricValue(value=None, status="unavailable", source="sales", note="missing"),
            returns_count=MetricValue(value=None, status="unavailable", source="sales", note="missing"),
            orders_amount=MetricValue(value=None, status="unavailable", source="orders", note="missing"),
            sales_amount=MetricValue(value=None, status="unavailable", source="sales", note="missing"),
            seller_payout=MetricValue(value=None, status="unavailable", source="realization", note="missing"),
            logistics_cost=MetricValue(value=None, status="unavailable", source="realization", note="missing"),
            storage_cost=MetricValue(value=None, status="unavailable", source="realization", note="missing"),
            deductions_amount=MetricValue(value=None, status="unavailable", source="realization", note="missing"),
            net_realization_amount=MetricValue(value=None, status="unavailable", source="realization", note="missing"),
        )
        metrics = MetricsBundle(run_context=context, financial=financial)

        facts = build_facts_bundle(metrics)
        section = facts.sections["financial"]
        items = {item.key: item for item in section.items}

        self.assertIsNone(items["orders_count"].value.value)
        self.assertIsNone(items["sales_amount"].value.value)
        self.assertNotEqual(items["orders_count"].value.value, 0)
        self.assertNotEqual(items["sales_amount"].value.value, 0)


if __name__ == "__main__":
    unittest.main()
