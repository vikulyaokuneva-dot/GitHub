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
from v4.metrics.financial.assembler import assemble_financial_metrics


class TestFinancialCostComponents(unittest.TestCase):
    def test_cost_components_are_separated(self) -> None:
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

        bundle = NormalizedBundle(
            run_context=context,
            realization=[
                NormalizedRealizationRecord("r1", None, 1, "2026-03-15", "sale", 500.0, 1.0, "realization", None),
                NormalizedRealizationRecord("r2", None, 1, "2026-03-15", "logistics", 50.0, None, "realization", None),
                NormalizedRealizationRecord("r3", None, 1, "2026-03-15", "storage", 30.0, None, "realization", None),
                NormalizedRealizationRecord("r4", None, 1, "2026-03-15", "deduction", 20.0, None, "realization", None),
                NormalizedRealizationRecord("r5", None, 1, "2026-03-15", "other", 7.0, None, "realization", None),
            ],
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.MISSING, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.MISSING, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
            },
        )

        financial = assemble_financial_metrics(bundle)

        self.assertEqual(financial.logistics_cost.value, 50.0)
        self.assertEqual(financial.storage_cost.value, 30.0)
        self.assertEqual(financial.deductions_amount.value, 20.0)
        self.assertEqual(financial.sales_amount.value, 500.0)
        self.assertEqual(financial.net_realization_amount.value, 400.0)


if __name__ == "__main__":
    unittest.main()
