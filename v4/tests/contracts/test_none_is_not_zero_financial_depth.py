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


class TestNoneIsNotZeroFinancialDepth(unittest.TestCase):
    def test_missing_component_not_converted_to_zero(self) -> None:
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
                NormalizedRealizationRecord("s", None, 1, "2026-03-15", "sale", 100.0, 1.0, "realization", None, None),
            ],
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.MISSING, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.MISSING, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
            },
        )

        financial = assemble_financial_metrics(bundle)

        self.assertIsNone(financial.commission_amount.value)
        self.assertEqual(financial.commission_amount.status, "partial")
        self.assertIsNone(financial.acquiring_amount.value)
        self.assertIsNone(financial.pvz_amount.value)
        self.assertNotEqual(financial.commission_amount.value, 0)


if __name__ == "__main__":
    unittest.main()
