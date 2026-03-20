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


class TestFinancialProfitLike(unittest.TestCase):
    def test_profit_like_with_explainable_formula(self) -> None:
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
                NormalizedRealizationRecord("s", None, 1, "2026-03-15", "sale", 1000.0, 1.0, "realization", None, "Продажа"),
                NormalizedRealizationRecord("c", None, 1, "2026-03-15", "deduction", 100.0, None, "realization", None, "Комиссия WB"),
                NormalizedRealizationRecord("a", None, 1, "2026-03-15", "deduction", 20.0, None, "realization", None, "Эквайринг"),
                NormalizedRealizationRecord("l", None, 1, "2026-03-15", "logistics", 50.0, None, "realization", None, "Логистика"),
                NormalizedRealizationRecord("st", None, 1, "2026-03-15", "storage", 10.0, None, "realization", None, "Хранение"),
                NormalizedRealizationRecord("p", None, 1, "2026-03-15", "deduction", 5.0, None, "realization", None, "ПВЗ"),
                NormalizedRealizationRecord("pen", None, 1, "2026-03-15", "deduction", 15.0, None, "realization", None, "Штраф"),
                NormalizedRealizationRecord("o", None, 1, "2026-03-15", "other", 25.0, None, "realization", None, "Сервисная корректировка"),
                NormalizedRealizationRecord("d", None, 1, "2026-03-15", "deduction", 30.0, None, "realization", None, "Удержание"),
            ],
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.MISSING, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.MISSING, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
            },
        )

        financial = assemble_financial_metrics(bundle)

        self.assertEqual(financial.gross_profit_like.value, 745.0)
        self.assertIsNotNone(financial.profit_formula_note)
        self.assertIn("net_profit_like", str(financial.profit_formula_note))
        self.assertEqual(financial.net_profit_like.value, 745.0)
        self.assertEqual(financial.net_profit_like.status, "confirmed")
        self.assertEqual(financial.financial_model_mode, "exact")
        self.assertEqual(financial.financial_confidence, "high")
        self.assertEqual(financial.financial_mode, "full")
        self.assertEqual(financial.margin.status, "confirmed")


if __name__ == "__main__":
    unittest.main()
