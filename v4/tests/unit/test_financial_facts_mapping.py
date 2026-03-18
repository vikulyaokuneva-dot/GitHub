from __future__ import annotations

import unittest

from v4.core.contracts import FinancialMetricsSection, MetricValue, MetricsBundle, RunContext, RunMode
from v4.outputs.facts.builder import build_facts_bundle


def _metric(value, status="confirmed", source="financial", note=None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


def _find_item(section, key: str):
    for item in section.items:
        if item.key == key:
            return item
    raise AssertionError(f"Fact item '{key}' not found")


class TestFinancialFactsMapping(unittest.TestCase):
    def test_financial_metrics_mapped_without_recompute(self) -> None:
        financial = FinancialMetricsSection(
            orders_count=_metric(10),
            sales_count=_metric(8),
            returns_count=_metric(2),
            orders_amount=_metric(1000.0),
            sales_amount=_metric(900.0),
            seller_payout=_metric(700.0),
            logistics_cost=_metric(50.0),
            storage_cost=_metric(10.0),
            deductions_amount=_metric(5.0),
            net_realization_amount=_metric(635.0, status="partial", note="partial realization"),
            revenue_gross=_metric(950.0),
            commission_amount=_metric(120.0),
            acquiring_amount=_metric(15.0),
            pvz_amount=_metric(7.0),
            penalties_amount=_metric(None, status="unavailable", note="no penalties data"),
            other_costs_amount=_metric(3.0),
            gross_profit_like=_metric(780.0, status="partial"),
            net_profit_like=_metric(None, status="unavailable", note="insufficient components"),
            profit_formula_note="gross_profit_like = revenue_gross - identifiable_costs",
            source_quality={"orders": "ok", "sales": "ok", "realization": "partial"},
            component_quality={"revenue": "ok", "commission": "ok", "penalties": "missing"},
            warnings=["realization lag fallback used"],
        )

        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        metrics = MetricsBundle(run_context=context, financial=financial)

        facts = build_facts_bundle(metrics)
        section = facts.sections["financial"]

        orders_item = _find_item(section, "orders_count")
        self.assertEqual(orders_item.value.value, 10)
        self.assertEqual(orders_item.value.status, "confirmed")

        payout_item = _find_item(section, "seller_payout")
        self.assertEqual(payout_item.value.value, 700.0)

        net_profit_item = _find_item(section, "net_profit_like")
        self.assertIsNone(net_profit_item.value.value)
        self.assertEqual(net_profit_item.value.status, "unavailable")

        gross_profit_item = _find_item(section, "gross_profit_like")
        self.assertIn("profit_formula_note", gross_profit_item.diagnostics)
        self.assertEqual(
            section.diagnostics.get("profit_formula_note"),
            "gross_profit_like = revenue_gross - identifiable_costs",
        )


if __name__ == "__main__":
    unittest.main()
