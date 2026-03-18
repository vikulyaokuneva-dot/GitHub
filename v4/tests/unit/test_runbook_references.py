from __future__ import annotations

import unittest
from pathlib import Path


class TestRunbookReferences(unittest.TestCase):
    def test_runbook_contains_required_commands_and_paths(self) -> None:
        content = Path("v4/RUNBOOK.md").read_text(encoding="utf-8")

        self.assertIn("python -m unittest discover v4/tests", content)
        self.assertIn("python -m compileall v4", content)
        self.assertIn("python v4/scripts/smoke_run_daily.py", content)
        self.assertIn("python v4/scripts/smoke_run_audit.py", content)
        self.assertIn("python v4/scripts/ci_smoke_audit.py", content)
        self.assertIn("audit_file_mode", content)
        self.assertIn("--output-dir", content)
        self.assertIn("facts.json", content)
        self.assertIn("decisions.json", content)
        self.assertIn("outputs_summary.json", content)
        self.assertIn("diagnostics", content)


if __name__ == "__main__":
    unittest.main()
