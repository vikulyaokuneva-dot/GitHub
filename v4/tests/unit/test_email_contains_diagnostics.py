from __future__ import annotations

import unittest

from v4.core.contracts import DecisionsBundle, FactsBundle, RunContext, RunMode
from v4.delivery.email.formatter import format_email_body
from v4.outputs.email.builder import build_email_payload


class TestEmailContainsDiagnostics(unittest.TestCase):
    def test_diagnostics_block_is_visible(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-19",
            resolved_date="2026-03-19",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
            dry_run=False,
        )
        facts = FactsBundle(run_context=context)
        decisions = DecisionsBundle(run_context=context, items=[])
        diagnostics = {
            "job": {
                "source_availability": {"orders": "ok", "sales": "missing", "funnel": "partial"},
                "missing_sources": ["sales"],
                "warnings": ["financial lag detected"],
            },
            "summary": {"partial_flag": True, "selected_production_mode": "v4"},
            "production": {
                "selected_mode": "v4",
                "switch_reason": "explicit CLI production override",
                "rollback_happened": False,
                "fallback_used": False,
            },
        }

        payload = build_email_payload(facts, decisions, diagnostics=diagnostics, full_debug=True)
        body = format_email_body(payload)

        self.assertIn("production_mode: v4", body)
        self.assertIn("mode_resolution_reason: explicit CLI production override", body)
        self.assertIn("partial_flag: true", body)
        self.assertIn("missing_sources: ['sales']", body)
        self.assertIn("financial lag detected", body)


if __name__ == "__main__":
    unittest.main()

