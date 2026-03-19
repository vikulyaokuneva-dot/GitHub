from __future__ import annotations

import unittest
from pathlib import Path


class TestReleaseChecklistReferences(unittest.TestCase):
    def test_release_checklist_contains_required_gates(self) -> None:
        content = Path("v4/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

        self.assertIn("python -m unittest discover v4/tests", content)
        self.assertIn("python -m compileall v4", content)
        self.assertIn("python v4/scripts/smoke_run_daily.py", content)
        self.assertIn("python v4/scripts/smoke_run_audit.py", content)
        self.assertIn("facts.json", content)
        self.assertIn("decisions.json", content)
        self.assertIn("outputs_summary.json", content)
        self.assertIn("diagnostics.job", content)
        self.assertIn("diagnostics.summary", content)
        self.assertIn("output_dir", content)
        self.assertIn("KPI", content)
        self.assertIn("metrics", content)

    def test_runbook_links_release_checklist(self) -> None:
        content = Path("v4/RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("RELEASE_CHECKLIST.md", content)


if __name__ == "__main__":
    unittest.main()
