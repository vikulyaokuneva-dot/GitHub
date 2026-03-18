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


class TestFinancialComponentsClassification(unittest.TestCase):
    def test_components_are_separated(self) -> None:
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
                NormalizedRealizationRecord("r1", None, 1, "2026-03-15", "sale", 1000.0, 1.0, "realization", None, "Продажа"),
                NormalizedRealizationRecord("r2", None, 1, "2026-03-15", "logistics", 50.0, None, "realization", None, "Логистика"),
                NormalizedRealizationRecord("r3", None, 1, "2026-03-15", "storage", 20.0, None, "realization", None, "Хранение"),
                NormalizedRealizationRecord("r4", None, 1, "2026-03-15", "deduction", 70.0, None, "realization", None, "Удержание"),
                NormalizedRealizationRecord("r5", None, 1, "2026-03-15", "deduction", 90.0, None, "realization", None, "Вознаграждение WB комиссия"),
                NormalizedRealizationRecord("r6", None, 1, "2026-03-15", "deduction", 12.0, None, "realization", None, "Эквайринг"),
                NormalizedRealizationRecord("r7", None, 1, "2026-03-15", "deduction", 5.0, None, "realization", None, "ПВЗ выдача"),
                NormalizedRealizationRecord("r8", None, 1, "2026-03-15", "deduction", 8.0, None, "realization", None, "Штраф"),
                NormalizedRealizationRecord("r9", None, 1, "2026-03-15", "other", 3.0, None, "realization", None, "Сервисная корректировка"),
            ],
            source_statuses={
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True)
            },
        )

        totals = classify_realization_components(bundle, actual_date="2026-03-15")

        self.assertEqual(totals.revenue_gross, 1000.0)
        self.assertEqual(totals.logistics_cost, 50.0)
        self.assertEqual(totals.storage_cost, 20.0)
        self.assertEqual(totals.deductions_amount, 70.0)
        self.assertEqual(totals.commission_amount, 90.0)
        self.assertEqual(totals.acquiring_amount, 12.0)
        self.assertEqual(totals.pvz_amount, 5.0)
        self.assertEqual(totals.penalties_amount, 8.0)
        self.assertEqual(totals.other_costs_amount, 3.0)


if __name__ == "__main__":
    unittest.main()
