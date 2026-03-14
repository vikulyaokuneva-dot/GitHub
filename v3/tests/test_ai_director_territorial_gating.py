import unittest

from src.analysis.ai_director import build_strategy_plan


class TestAiDirectorTerritorialGating(unittest.TestCase):
    def test_no_rebalance_tasks_when_territorial_is_preview(self) -> None:
        metrics = {
            "data_quality": {
                "sku_attribution_status": "ok",
                "territorial_analysis_enabled": True,
                "territorial_analysis_mode": "preview",
                "territorial_recommendation_status": "watch",
                "territorial_actionable_enabled": False,
            },
            "sku_metrics": [
                {"sku": "SKU1", "profit": 100.0, "revenue": 1000.0, "orders": 20},
            ],
        }
        territorial_distribution = {
            "summary": {
                "analysis_mode": "preview",
                "recommendation_status": "watch",
                "suppressed_due_to_data_quality": True,
                "demand_coverage_pct": 30.0,
                "stock_coverage_pct": 0.0,
                "coverage_pct": 20.0,
            },
            "items": [{"sku": "SKU1", "ktr": 1.8, "analysis_mode": "preview", "recommendation_status": "watch"}],
        }

        payload = build_strategy_plan(
            metrics,
            abc_rows=[],
            health_payload={},
            territorial_distribution=territorial_distribution,
            logistics_ktr={"items": [{"sku": "SKU1", "ktr": 1.8}]},
            opportunity_scores={},
            growth_simulation={},
        )

        tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        task_names = {str(row.get("task") or "") for row in tasks if isinstance(row, dict)}

        self.assertNotIn("rebalance_stock", task_names)
        self.assertIn("collect_stock_distribution_data", task_names)
        self.assertIn("connect_stock_source", task_names)
        self.assertIn("improve_regional_demand_attribution", task_names)


if __name__ == "__main__":
    unittest.main()
