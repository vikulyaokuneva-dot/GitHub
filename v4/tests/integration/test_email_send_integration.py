from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from v4.delivery.email.formatter import format_email_body
from v4.pipeline.runners.daily_runner import run_daily_pipeline
from v4.pipeline.stages.delivery_stage import run_delivery_stage


class TestEmailSendIntegration(unittest.TestCase):
    def test_email_send_is_called_with_non_empty_body_and_diagnostics(self) -> None:
        with patch.dict(os.environ, {"WB_API_TOKEN": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = run_daily_pipeline(
                    run_context={
                        "seller_id": "seller_001",
                        "run_date": "2026-03-19",
                        "timezone": "Europe/Moscow",
                    },
                    output_dir=tmpdir,
                )

                with patch(
                    "v4.pipeline.stages.delivery_stage.send_email_via_smtp",
                    return_value={
                        "email_transport_status": "success",
                        "email_failure_reason_normalized": "",
                    },
                ) as send_mock:
                    delivery = run_delivery_stage(
                        outputs=result["outputs"],
                        output_dir=tmpdir,
                        enable_pdf_render=True,
                        enable_email_preview=True,
                        enable_email_send=True,
                    )

        send_mock.assert_called_once()
        payload = send_mock.call_args.args[0]
        body = format_email_body(payload)
        self.assertTrue(str(body).strip())
        self.assertIn("diagnostics", delivery)
        self.assertTrue(delivery["diagnostics"]["email_send_attempted"])
        self.assertTrue(delivery["diagnostics"]["email_sent"])


if __name__ == "__main__":
    unittest.main()

