from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from v4.entry.daily import run as run_daily


class TestForceEmailDailyPath(unittest.TestCase):
    def test_force_email_requires_wb_api_token(self) -> None:
        with patch.dict(os.environ, {"WB_API_TOKEN": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "WB API token is required for real run"):
                run_daily(
                    {
                        "seller_id": "seller_001",
                        "run_date": "2026-03-19",
                        "output_dir": ".tmp/v4_outputs/test_force_email",
                        "production_mode": "v4",
                        "force_email": True,
                    }
                )

    def test_force_email_fails_when_delivery_send_failed(self) -> None:
        fake_result = {
            "run_context": {},
            "diagnostics": {"summary": {"mode": "daily_api_mode", "partial_flag": False}},
            "metrics": {},
            "facts": {},
            "decisions": {},
            "outputs": {"artifacts": {"saved_files": {}}},
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"WB_API_TOKEN": "token"}, clear=False),
                patch("v4.entry.daily.run_production_daily", return_value={"run_result": fake_result, "production": {"diagnostics": {"selected_mode": "v4"}}}),
                patch("v4.entry.daily._inject_full_email_debug_payload", return_value=True),
                patch("v4.entry.daily._persist_diagnostics_artifact", return_value=None),
                patch(
                    "v4.entry.daily.run_delivery_stage",
                    return_value={
                        "pdf_path": None,
                        "email_preview_path": None,
                        "email_send": {
                            "email_transport_status": "failed",
                            "email_failure_reason_normalized": "smtp auth failed",
                        },
                        "diagnostics": {
                            "email_send_attempted": True,
                            "email_sent": False,
                            "email_send": {
                                "email_transport_status": "failed",
                                "email_failure_reason_normalized": "smtp auth failed",
                            },
                        },
                    },
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "Email send failed: smtp auth failed"):
                    run_daily(
                        {
                            "seller_id": "seller_001",
                            "run_date": "2026-03-19",
                            "output_dir": tmpdir,
                            "production_mode": "v4",
                            "force_email": True,
                        }
                    )


if __name__ == "__main__":
    unittest.main()
