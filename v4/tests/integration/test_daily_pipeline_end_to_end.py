from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from v4.pipeline.runners.daily_runner import run_daily_pipeline


class TestDailyPipelineEndToEnd(unittest.TestCase):
    def test_daily_pipeline_end_to_end_partial_safe(self) -> None:
        with patch.dict(os.environ, {"WB_API_TOKEN": ""}, clear=False):
            result = run_daily_pipeline(
                run_context={
                    "seller_id": "seller_001",
                    "run_date": "2026-03-15",
                    "timezone": "Europe/Moscow",
                },
                output_dir=None,
            )

        self.assertIn("run_context", result)
        self.assertIn("diagnostics", result)
        self.assertIn("metrics", result)
        self.assertIn("facts", result)
        self.assertIn("decisions", result)
        self.assertIn("outputs", result)
        self.assertIn("warnings", result)

        self.assertIn("job", result["diagnostics"])
        self.assertIn("summary", result["diagnostics"])

        self.assertIn("artifacts", result["outputs"])
        self.assertEqual(result["outputs"]["artifacts"]["saved_files"], {})


if __name__ == "__main__":
    unittest.main()
