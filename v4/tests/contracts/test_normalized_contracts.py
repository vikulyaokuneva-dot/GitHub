from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedOrderRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)


class TestNormalizedContracts(unittest.TestCase):
    def test_bundle_accepts_empty_lists_and_statuses(self) -> None:
        run_context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=date(2026, 3, 15),
            resolved_date=date(2026, 3, 15),
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        statuses = {
            "orders": SourceStatus(
                source_name="orders",
                kind=SourceKind.API,
                status=SourceStatusCode.MISSING,
                is_required=True,
                rows_loaded=None,
            )
        }

        bundle = NormalizedBundle(run_context=run_context, source_statuses=statuses)

        self.assertEqual(bundle.orders, [])
        self.assertEqual(bundle.sales, [])
        self.assertEqual(bundle.source_statuses["orders"].status, SourceStatusCode.MISSING)

    def test_none_is_not_zero_in_records(self) -> None:
        record = NormalizedOrderRecord(
            record_id=None,
            seller_id=None,
            nm_id=None,
            subject_name=None,
            quantity=None,
            price=None,
            order_date=None,
            source_tag="orders",
            raw_ref=None,
        )
        self.assertIsNone(record.quantity)
        self.assertIsNone(record.price)
        self.assertNotEqual(record.quantity, 0)
        self.assertNotEqual(record.price, 0)


if __name__ == "__main__":
    unittest.main()
