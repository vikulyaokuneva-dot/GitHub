from __future__ import annotations

import unittest

from v4.core.contracts import DecisionItem, DecisionPriority, DecisionStatus, DecisionsBundle, FactsBundle, RunContext, RunMode
from v4.delivery.email.formatter import format_email_body
from v4.outputs.email.builder import build_email_payload


class TestEmailContainsDecisionsEvenIfUnavailable(unittest.TestCase):
    def test_decision_catalog_shown_when_not_triggered(self) -> None:
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
        facts = FactsBundle(run_context=context)
        decisions = DecisionsBundle(run_context=context, items=[])

        payload = build_email_payload(facts, decisions, full_debug=True)
        body = format_email_body(payload)

        self.assertIn("[partial] DECISIONS", body)
        self.assertIn("negative_profit", body)
        self.assertIn("status=not_triggered", body)
        self.assertIn("rule not triggered", body)

    def test_partial_decision_is_rendered_as_unavailable_not_triggered(self) -> None:
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
        facts = FactsBundle(run_context=context)
        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="negative_profit",
                    title="Negative profit",
                    summary="Cannot confirm negative profit due to incomplete financial evidence.",
                    priority=DecisionPriority.P1,
                    status=DecisionStatus.PARTIAL,
                    section="financial",
                    reason="profit-like evidence is incomplete",
                )
            ],
        )

        payload = build_email_payload(facts, decisions, full_debug=True)
        body = format_email_body(payload)

        self.assertIn("negative_profit", body)
        self.assertIn("status=unavailable", body)
        self.assertNotIn("status=triggered | Cannot confirm", body)


if __name__ == "__main__":
    unittest.main()
