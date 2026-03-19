from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    DecisionsBundle,
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    RunContext,
    RunMode,
)
from v4.outputs.email.builder import build_email_payload
from v4.outputs.pdf.builder import build_pdf_payload


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


class TestHealthOutputPayloads(unittest.TestCase):
    def test_health_section_is_included_in_email_and_pdf_payloads(self) -> None:
        health = FactSection(
            section_name="health",
            title="Health",
            status="partial",
            items=[
                FactItem(
                    key="business_health_score",
                    title="Business health score",
                    value=FactValue(value=None, status="partial", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="score_status",
                    title="Score status",
                    value=FactValue(value="partial", status="partial", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="sku_health_signals_count",
                    title="SKU health signals count",
                    value=FactValue(value=2, status="partial", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="problematic_sku_count",
                    title="Problematic SKU count",
                    value=FactValue(value=3, status="partial", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="dead_stock_risk_count",
                    title="Dead stock risk count",
                    value=FactValue(value=None, status="unavailable", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="overstock_risk_count",
                    title="Overstock risk count",
                    value=FactValue(value=1, status="confirmed", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="component_profitability_score",
                    title="Component profitability score",
                    value=FactValue(value=10.0, status="confirmed", source="financial", note=None),
                    category="health",
                ),
            ],
            diagnostics={"source_quality": {"funnel": "partial"}},
        )
        facts = FactsBundle(
            run_context=_context(),
            sections={"health": health},
            data_quality={"partial_sections": ["health"], "unavailable_sections": []},
        )
        decisions = DecisionsBundle(run_context=facts.run_context)

        email_payload = build_email_payload(facts, decisions, mode="daily")
        pdf_payload = build_pdf_payload(facts, decisions, mode="daily")

        email_titles = [section.title for section in email_payload.sections]
        self.assertIn("Health", email_titles)
        health_section = next(section for section in email_payload.sections if section.title == "Health")
        self.assertTrue(any("Business health score: нет данных (частично)" in line for line in health_section.lines))
        self.assertTrue(any(line.startswith("Health score:") for line in email_payload.summary_lines))

        page_titles = [page.title for page in pdf_payload.pages]
        self.assertIn("Health", page_titles)
        health_page = next(page for page in pdf_payload.pages if page.title == "Health")
        rows = {row["label"]: row for row in health_page.blocks[0].rows}
        self.assertEqual(rows["Business health score"]["value"], "частично")
        self.assertEqual(rows["Dead stock risk count"]["value"], "нет данных")


if __name__ == "__main__":
    unittest.main()

