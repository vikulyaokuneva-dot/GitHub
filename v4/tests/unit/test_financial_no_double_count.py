from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedRealizationRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.financial.components import classify_realization_components


class TestFinancialNoDoubleCount(unittest.TestCase):
    def test_single_event_counted_once(self) -> None:
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
        amount = 100.0
        bundle = NormalizedBundle(
            run_context=context,
            realization=[
                NormalizedRealizationRecord(
                    "evt", None, 1, "2026-03-15", "deduction", amount, None, "realization", None, "Эквайринг комиссия"
                ),
            ],
            source_statuses={
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
            },
        )

        totals = classify_realization_components(bundle, actual_date="2026-03-15")
        buckets = [
            totals.commission_amount,
            totals.acquiring_amount,
            totals.pvz_amount,
            totals.penalties_amount,
            totals.deductions_amount,
            totals.other_costs_amount,
            totals.logistics_cost,
            totals.storage_cost,
        ]
        summed = sum(float(value or 0.0) for value in buckets)

        self.assertEqual(summed, amount)


if __name__ == "__main__":
    unittest.main()
