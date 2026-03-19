from __future__ import annotations

import unittest
from pathlib import Path


class TestScheduleConfig(unittest.TestCase):
    def test_v4_schedule_workflow_has_0600_msk_cron(self) -> None:
        workflow = Path(".github/workflows/v4-daily-0600-msk.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "0 3 * * *"', workflow)
        self.assertIn("06:00 Europe/Moscow", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("V4_SCHEDULE_ENABLED", workflow)
        self.assertIn("EMAIL_USERNAME", workflow)
        self.assertIn("EMAIL_PASSWORD", workflow)
        self.assertIn("EMAIL_TO", workflow)
        self.assertIn("WB_API_TOKEN", workflow)
        self.assertIn("--force-email", workflow)


if __name__ == "__main__":
    unittest.main()
