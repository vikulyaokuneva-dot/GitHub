from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import NormalizedBundle, RunContext, RunMode, SourceKind, SourceStatus, SourceStatusCode
from v4.metrics.core.engine import build_metrics_bundle


class TestNoneIsNotZeroMetrics(unittest.TestCase):
    def test_missing_sources_keep_none_values(self) -> None:
        d = date(2026, 3, 15)
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=d,
            resolved_date=d,
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        normalized = NormalizedBundle(
            run_context=context,
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.MISSING, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.ERROR, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.MISSING, True),
            },
        )

        metrics = build_metrics_bundle(normalized)
        financial = metrics.financial
        assert financial is not None

        self.assertIsNone(financial.orders_count.value)
        self.assertIsNone(financial.sales_count.value)
        self.assertIsNone(financial.seller_payout.value)
        self.assertIsNone(financial.net_realization_amount.value)
        self.assertNotEqual(financial.orders_count.value, 0)
        self.assertEqual(financial.orders_count.status, "unavailable")


if __name__ == "__main__":
    unittest.main()
