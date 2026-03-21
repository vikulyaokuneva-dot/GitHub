from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedFunnelRecord,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
    NormalizedStockRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.pipeline.stages.decisions_stage import run as run_decisions_stage
from v4.pipeline.stages.facts_stage import run as run_facts_stage
from v4.pipeline.stages.metrics_stage import run as run_metrics_stage
from v4.pipeline.stages.outputs_stage import run as run_outputs_stage


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
    )


class TestHealthPipelineIntegration(unittest.TestCase):
    def test_health_passes_metrics_to_outputs_chain(self) -> None:
        normalized = NormalizedBundle(
            run_context=_context(),
            orders=[NormalizedOrderRecord("o1", "seller_001", 1001, None, 1, 100.0, "2026-03-15", "orders", None)],
            sales=[NormalizedSaleRecord("s1", "seller_001", 1001, 1, 100.0, 20.0, "2026-03-15", "sale", False, "sales", None)],
            realization=[
                NormalizedRealizationRecord("r1", "seller_001", 1001, "2026-03-15", "sale", 20.0, 1.0, "realization", None),
                NormalizedRealizationRecord("r2", "seller_001", 1001, "2026-03-15", "logistics", 5.0, None, "realization", None),
                NormalizedRealizationRecord("r3", "seller_001", 1001, "2026-03-15", "storage", 5.0, None, "realization", None),
                NormalizedRealizationRecord("r4", "seller_001", 1001, "2026-03-15", "deduction", 4.0, None, "realization", None),
            ],
            stocks=[
                NormalizedStockRecord("stk1", "seller_001", 1001, "WH-A", "M", 100, "2026-03-15", "stocks", "st1"),
                NormalizedStockRecord("stk2", "seller_001", 1002, "WH-B", "M", 1000, "2026-03-15", "stocks", "st2"),
            ],
            funnel=[
                NormalizedFunnelRecord(1001, "2026-03-15", 200.0, 80.0, 30.0, 0.0, 0.0, "funnel", "f1"),
                NormalizedFunnelRecord(1002, "2026-03-15", 150.0, 60.0, 20.0, 1.0, 0.0, "funnel", "f2"),
            ],
            source_statuses={
                "orders": _status("orders", SourceStatusCode.OK, True),
                "sales": _status("sales", SourceStatusCode.OK, True),
                "realization": _status("realization", SourceStatusCode.OK, True),
                "funnel": _status("funnel", SourceStatusCode.OK, False),
                "ads_campaigns": _status("ads_campaigns", SourceStatusCode.MISSING, False),
                "ads_stats": _status("ads_stats", SourceStatusCode.MISSING, False),
                "stocks": _status("stocks", SourceStatusCode.OK, False),
            },
        )

        metrics = run_metrics_stage(normalized)
        self.assertIsNotNone(metrics.health)
        assert metrics.health is not None
        self.assertIn("health", metrics.diagnostics.get("metrics_sections_built", []))

        facts = run_facts_stage(metrics)
        self.assertIn("health", facts.sections)

        decisions = run_decisions_stage(facts)
        decision_codes = {item.code for item in decisions.items}
        self.assertIn("weak_conversion", decision_codes)
        self.assertIn("dead_sku", decision_codes)
        self.assertIn("overstock", decision_codes)

        outputs = run_outputs_stage(facts, decisions, mode="daily", output_dir=None)
        email_payload = outputs["email"]
        pdf_payload = outputs["pdf"]

        self.assertTrue(any(section.title == "Health" for section in email_payload.sections))
        self.assertTrue(any(page.title == "Оценка товаров" for page in pdf_payload.pages))


if __name__ == "__main__":
    unittest.main()
