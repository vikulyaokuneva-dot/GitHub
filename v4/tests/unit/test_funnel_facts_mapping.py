from __future__ import annotations

import unittest

from v4.core.contracts import FunnelMetricsSection, MetricValue, MetricsBundle, RunContext, RunMode
from v4.outputs.facts.builder import build_facts_bundle


def _metric(value, status="confirmed", source="funnel", note=None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


class TestFunnelFactsMapping(unittest.TestCase):
    def test_funnel_metrics_map_preserving_status(self) -> None:
        funnel = FunnelMetricsSection(
            impressions=_metric(1000.0),
            opens=_metric(500.0),
            cart_adds=_metric(None, status="partial", note="missing in some rows"),
            orders=_metric(120.0),
            buys=_metric(90.0),
            ctr_open_from_impressions=_metric(0.5),
            cr_cart_from_opens=_metric(None, status="partial", note="denominator missing"),
            cr_orders_from_cart=_metric(None, status="unavailable", note="cart adds unavailable"),
            cr_buys_from_orders=_metric(0.75),
            cr_buys_from_impressions=_metric(0.09),
            source_quality={"funnel": "partial"},
            warnings=["funnel field cart_adds partially populated"],
            note="funnel metrics are partial",
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
        metrics = MetricsBundle(run_context=context, funnel=funnel)

        facts = build_facts_bundle(metrics)
        section = facts.sections["funnel"]

        items = {item.key: item for item in section.items}
        self.assertEqual(items["impressions"].value.value, 1000.0)
        self.assertEqual(items["cart_adds"].value.status, "partial")
        self.assertIsNone(items["cr_orders_from_cart"].value.value)
        self.assertEqual(items["cr_orders_from_cart"].value.status, "unavailable")
        self.assertEqual(section.status, "partial")
        self.assertIn("source_quality", section.diagnostics)


if __name__ == "__main__":
    unittest.main()
