from __future__ import annotations

import unittest

from v4.core.contracts import DecisionsBundle, FactsBundle, RunContext, RunMode
from v4.delivery.email.formatter import format_email_body
from v4.outputs.email.builder import build_email_payload


class TestEmailShowsUnavailableSections(unittest.TestCase):
    def test_unavailable_sections_are_not_hidden(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-19",
            resolved_date="2026-03-19",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
            dry_run=False,
        )
        facts = FactsBundle(
            run_context=context,
            sections={},
            data_quality={"partial_sections": [], "unavailable_sections": ["financial", "ads", "funnel"]},
            warnings=["all sections unavailable"],
        )
        decisions = DecisionsBundle(run_context=context, items=[])

        payload = build_email_payload(
            facts,
            decisions,
            mode="daily",
            diagnostics={"summary": {"partial_flag": True}},
            full_debug=True,
        )
        body = format_email_body(payload)

        self.assertIn("[unavailable] FINANCIAL SUMMARY", body)
        self.assertIn("[unavailable] ADS", body)
        self.assertIn("[unavailable] FUNNEL", body)
        self.assertIn("нет данных", body)


if __name__ == "__main__":
    unittest.main()

