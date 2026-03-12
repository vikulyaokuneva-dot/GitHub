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
            settings = ResearchEngineSettings(
                project_root=tmp_path,
                artifacts_dir=tmp_path / "artifacts",
            )
            runner = ResearchPipelineRunner(
                settings=settings,
                research_config=ResearchConfig(shortlist_size=2),
            )

            result = runner.run()

            self.assertGreaterEqual(result.candidates_count, 3)
            self.assertEqual(result.shortlisted_count, 2)
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
            self.assertIn("shortlisted_count", summary)
            self.assertEqual(summary["shortlisted_count"], 2)


if __name__ == "__main__":
    unittest.main()
