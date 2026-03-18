from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.financial.assembler import assemble_financial_metrics


def _context() -> RunContext:
    d = date(2026, 3, 15)
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date=d,
        resolved_date=d,
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


def _status(name: str, code: SourceStatusCode, required: bool) -> SourceStatus:
    return SourceStatus(
        source_name=name,
        kind=SourceKind.API,
        status=code,
        is_required=required,
        rows_loaded=None,
    )


class TestFinancialAssemblerBasic(unittest.TestCase):
    def test_basic_financial_calculation(self) -> None:
        bundle = NormalizedBundle(
            run_context=_context(),
            orders=[
                NormalizedOrderRecord("o1", "seller_001", 1, None, 2, 100.0, "2026-03-15", "orders", None),
                NormalizedOrderRecord("o2", "seller_001", 2, None, 1, 50.0, "2026-03-15", "orders", None),
            ],
            sales=[
                NormalizedSaleRecord("s1", "seller_001", 1, 1, 300.0, 220.0, "2026-03-15", "sale", False, "sales", None),
                NormalizedSaleRecord("s2", "seller_001", 1, 1, 100.0, -20.0, "2026-03-15", "return", True, "sales", None),
            ],
            realization=[
                NormalizedRealizationRecord("r1", "seller_001", 1, "2026-03-15", "sale", 220.0, 1.0, "realization", None),
                NormalizedRealizationRecord("r2", "seller_001", 1, "2026-03-15", "return", -20.0, 1.0, "realization", None),
                NormalizedRealizationRecord("r3", "seller_001", 1, "2026-03-15", "logistics", 100.0, None, "realization", None),
                NormalizedRealizationRecord("r4", "seller_001", 1, "2026-03-15", "storage", 20.0, None, "realization", None),
                NormalizedRealizationRecord("r5", "seller_001", 1, "2026-03-15", "deduction", 10.0, None, "realization", None),
            ],
            source_statuses={
                "orders": _status("orders", SourceStatusCode.OK, True),
                "sales": _status("sales", SourceStatusCode.OK, True),
                "realization": _status("realization", SourceStatusCode.OK, True),
            },
        )

        financial = assemble_financial_metrics(bundle)

        self.assertEqual(financial.orders_count.value, 2)
        self.assertEqual(financial.sales_count.value, 1)
        self.assertEqual(financial.returns_count.value, 1)
        self.assertEqual(financial.orders_amount.value, 250.0)
        self.assertEqual(financial.sales_amount.value, 300.0)
        self.assertEqual(financial.seller_payout.value, 200.0)
        self.assertEqual(financial.net_realization_amount.value, 170.0)

    def test_missing_components_produce_partial_or_unavailable(self) -> None:
        bundle = NormalizedBundle(
            run_context=_context(),
            sales=[
                NormalizedSaleRecord("s1", "seller_001", 1, 1, None, None, "2026-03-15", "sale", False, "sales", None),
            ],
            source_statuses={
                "orders": _status("orders", SourceStatusCode.MISSING, True),
                "sales": _status("sales", SourceStatusCode.PARTIAL, True),
                "realization": _status("realization", SourceStatusCode.MISSING, True),
            },
        )

        financial = assemble_financial_metrics(bundle)
        self.assertIsNone(financial.orders_count.value)
        self.assertEqual(financial.orders_count.status, "unavailable")
        self.assertIsNone(financial.sales_amount.value)
        self.assertEqual(financial.sales_amount.status, "partial")
        self.assertIsNone(financial.net_realization_amount.value)


if __name__ == "__main__":
    unittest.main()
