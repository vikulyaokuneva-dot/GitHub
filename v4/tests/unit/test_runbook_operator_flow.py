from __future__ import annotations

import unittest
from pathlib import Path


class TestRunbookOperatorFlow(unittest.TestCase):
    def test_runbook_documents_preflight_smoke_manual_and_schedule(self) -> None:
        content = Path("v4/RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("python -m v4.entry.cli preflight", content)
        self.assertIn("python -m v4.entry.cli smoke", content)
        self.assertIn("python -m v4.entry.cli daily", content)
        self.assertIn("v4-daily-0600-msk.yml", content)
        self.assertIn('cron: "0 3 * * *"', content)
        self.assertIn("V4_SCHEDULE_ENABLED=false", content)


if __name__ == "__main__":
    unittest.main()

