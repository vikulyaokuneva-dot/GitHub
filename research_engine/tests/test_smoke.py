import json
import tempfile
import unittest
from pathlib import Path

from research_engine.config.research_config import ResearchConfig
from research_engine.config.settings import ResearchEngineSettings
from research_engine.pipeline import ResearchPipelineRunner


class TestResearchEngineSmoke(unittest.TestCase):
    def test_pipeline_starts_and_saves_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            scenarios_dir = tmp_path / "config" / "scenarios"
            scenarios_dir.mkdir(parents=True, exist_ok=True)
            scenario_path = scenarios_dir / "default_research_scenario.json"
            scenario_payload = {
                "scenario_name": "smoke_scenario",
                "budget_total": 210000,
                "target_price_min": 800,
                "target_price_max": 2600,
                "target_margin_pct": 24,
                "preferred_categories": [],
                "excluded_categories": ["fragile"],
                "max_competition_level": "medium",
                "notes": "scenario for smoke test",
            }
            scenario_path.write_text(json.dumps(scenario_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            settings = ResearchEngineSettings(
                project_root=tmp_path,
                artifacts_dir=tmp_path / "artifacts",
                scenarios_dir=scenarios_dir,
                default_scenario_path=scenario_path,
            )
            runner = ResearchPipelineRunner(
                settings=settings,
                research_config=ResearchConfig(shortlist_size=2),
            )

            result = runner.run()

            self.assertGreaterEqual(result.total_candidates, 20)
            self.assertGreaterEqual(result.filtered_candidates, 1)
            expected_files = [
                "research_job.json",
                "research_input.json",
                "research_candidates.json",
                "research_summary.json",
                "research_report.txt",
            ]
            for file_name in expected_files:
                self.assertTrue((settings.artifacts_dir / file_name).exists(), file_name)

            summary_path = settings.artifacts_dir / "research_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertIn("total_candidates", summary)
            self.assertIn("filtered_candidates", summary)
            self.assertGreaterEqual(summary["total_candidates"], summary["filtered_candidates"])

            input_path = settings.artifacts_dir / "research_input.json"
            input_payload = json.loads(input_path.read_text(encoding="utf-8"))
            self.assertEqual(input_payload["scenario_name"], "smoke_scenario")
            self.assertEqual(input_payload["budget_total"], 210000.0)

            candidates_path = settings.artifacts_dir / "research_candidates.json"
            candidates_payload = json.loads(candidates_path.read_text(encoding="utf-8"))
            self.assertEqual(candidates_payload["scenario_name"], "smoke_scenario")
            self.assertGreaterEqual(candidates_payload["total_candidates"], 20)
            self.assertGreaterEqual(candidates_payload["filtered_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
