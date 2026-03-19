from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    HealthMetricsSection,
    MetricValue,
    MetricsBundle,
    RunContext,
    RunMode,
)
from v4.outputs.facts.builder import build_facts_bundle


def _metric(value, status: str = "confirmed", source: str | None = "health", note: str | None = None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


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


class TestHealthFactsMapping(unittest.TestCase):
    def test_health_metrics_map_to_facts_transparently(self) -> None:
        health = HealthMetricsSection(
            business_health_score=_metric(47.5, status="partial", source="health_policy_v1"),
            sku_health_signals_count=_metric(2, status="partial", source="health_policy_v1"),
            problematic_sku_count=_metric(3, status="partial", source="health_policy_v1"),
            dead_stock_risk_count=_metric(1, status="confirmed", source="health_policy_v1"),
            overstock_risk_count=_metric(2, status="confirmed", source="health_policy_v1"),
            business_health_status_note="business health score is partial; missing components=['ads']",
            component_scores={
                "profitability": _metric(10.0, status="confirmed", source="financial"),
                "ads": _metric(None, status="unavailable", source="ads"),
                "funnel": _metric(8.0, status="partial", source="funnel"),
                "stock": _metric(12.0, status="confirmed", source="stocks"),
                "data_quality": _metric(4.0, status="partial", source="health_policy_v1"),
            },
            source_quality={"funnel": "partial", "stocks": "ok"},
            diagnostics={"policy": {"version": "health_policy_v1"}},
            warnings=["health warning"],
            note="health metrics are partial",
        )
        metrics = MetricsBundle(
            run_context=_context(),
            health=health,
            diagnostics={"metrics_sections_built": ["health"]},
        )

        facts = build_facts_bundle(metrics)
        self.assertIn("health", facts.sections)

        section = facts.sections["health"]
        items = {item.key: item for item in section.items}

        self.assertEqual(items["business_health_score"].value.value, 47.5)
        self.assertEqual(items["business_health_score"].value.status, "partial")
        self.assertEqual(items["score_status"].value.value, "partial")
        self.assertIn("component_profitability_score", items)
        self.assertIn("component_ads_score", items)
        self.assertIsNone(items["component_ads_score"].value.value)
        self.assertEqual(section.diagnostics.get("policy_version"), "health_policy_v1")


if __name__ == "__main__":
    unittest.main()

