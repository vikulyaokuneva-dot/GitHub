from __future__ import annotations

import unittest

from v4.core.contracts import FunnelMetricsSection, MetricStatus, MetricValue, MetricsBundle, RunContext, RunMode


class TestFunnelMetricsContracts(unittest.TestCase):
    def test_funnel_section_and_bundle_support_field(self) -> None:
        metric = MetricValue(value=10.0, status=MetricStatus.CONFIRMED.value, source="funnel")
        funnel = FunnelMetricsSection(
            impressions=metric,
            opens=metric,
            cart_adds=metric,
            orders=metric,
            buys=metric,
            ctr_open_from_impressions=metric,
            cr_cart_from_opens=metric,
            cr_orders_from_cart=metric,
            cr_buys_from_orders=metric,
            cr_buys_from_impressions=metric,
            source_quality={"funnel": "ok"},
            warnings=[],
            note=None,
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
        bundle = MetricsBundle(run_context=context, funnel=funnel)

        self.assertIsNotNone(bundle.funnel)
        assert bundle.funnel is not None
        self.assertEqual(bundle.funnel.impressions.value, 10.0)

    def test_none_not_replaced_with_zero(self) -> None:
        section = FunnelMetricsSection()
        self.assertIsNone(section.impressions.value)
        self.assertNotEqual(section.impressions.value, 0)


if __name__ == "__main__":
    unittest.main()
