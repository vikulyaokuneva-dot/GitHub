from __future__ import annotations

import unittest

from v4.core.contracts import DecisionsBundle, FactsBundle, RunContext, RunMode
from v4.outputs.email.builder import build_email_payload


class TestEmailNoHiddenSections(unittest.TestCase):
    def test_all_debug_sections_exist_even_with_empty_data(self) -> None:
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
        payload = build_email_payload(
            FactsBundle(run_context=context),
            DecisionsBundle(run_context=context, items=[]),
            full_debug=True,
        )

        titles = [section.title for section in payload.sections]
        self.assertEqual(len(titles), 11)
        self.assertEqual(
            titles,
            [
                "HEADER",
                "DATA AVAILABILITY",
                "FINANCIAL SUMMARY",
                "DAILY KPI",
                "FUNNEL",
                "ADS",
                "STOCK",
                "HEALTH",
                "DECISIONS",
                "DIAGNOSTICS",
                "FOOTER",
            ],
        )


if __name__ == "__main__":
    unittest.main()

