from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedRealizationRecord,
    RunContext,
    RunMode,
)
from v4.metrics.financial.lag_fallback import resolve_realization_window


def _context(target: str = "2026-03-15") -> RunContext:
    d = date.fromisoformat(target)
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date=d,
        resolved_date=d,
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


def _realization(event_date: str) -> NormalizedRealizationRecord:
    return NormalizedRealizationRecord(
        record_id=f"rr-{event_date}",
        seller_id="seller_001",
        nm_id=123,
        event_date=event_date,
        event_type="sale",
        amount=100.0,
        quantity=1.0,
        source_tag="realization",
        raw_ref=None,
    )


class TestRealizationLagFallback(unittest.TestCase):
    def test_exact_target_date_no_fallback(self) -> None:
        bundle = NormalizedBundle(
            run_context=_context(),
            realization=[_realization("2026-03-15")],
        )
        resolved = resolve_realization_window(bundle, bundle.run_context)
        self.assertEqual(resolved.target_date, "2026-03-15")
        self.assertEqual(resolved.actual_date, "2026-03-15")
        self.assertFalse(resolved.fallback_used)
        self.assertEqual(resolved.lag_days, 0)

    def test_previous_date_uses_fallback(self) -> None:
        bundle = NormalizedBundle(
            run_context=_context(),
            realization=[_realization("2026-03-14")],
        )
        resolved = resolve_realization_window(bundle, bundle.run_context)
        self.assertEqual(resolved.target_date, "2026-03-15")
        self.assertEqual(resolved.actual_date, "2026-03-14")
        self.assertTrue(resolved.fallback_used)
        self.assertEqual(resolved.lag_days, 1)

    def test_no_realization_data_unavailable(self) -> None:
        bundle = NormalizedBundle(run_context=_context(), realization=[])
        resolved = resolve_realization_window(bundle, bundle.run_context)
        self.assertIsNone(resolved.actual_date)
        self.assertFalse(resolved.fallback_used)
        self.assertEqual(resolved.status, "unavailable")


if __name__ == "__main__":
    unittest.main()
