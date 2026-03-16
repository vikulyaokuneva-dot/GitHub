import unittest

from v3.pipeline.run_summary_builder import build_run_summary


class TestRunSummaryEmailStatus(unittest.TestCase):
    def test_email_failure_is_tracked_without_overriding_pipeline_status(self) -> None:
        payload = build_run_summary(
            seller_id="seller_001",
            mode="daily",
            run_date="2026-03-16",
            started_at="2026-03-16T00:00:00Z",
            finished_at="2026-03-16T00:10:00Z",
            status="success",
            error=None,
            email_attempted=True,
            email_sent=False,
            email_to="te***@example.com",
            email_error="EMAIL DELIVERY FAILED [connect]: SMTP connection blocked by runtime environment",
            email_stage="connect",
            email_transport_status="failed",
            email_failure_reason_normalized="SMTP connection blocked by runtime environment",
        )

        self.assertEqual(str(payload.get("status") or ""), "success")
        self.assertTrue(bool(payload.get("email_attempted")))
        self.assertFalse(bool(payload.get("email_sent")))
        self.assertEqual(str(payload.get("email_stage") or ""), "connect")
        self.assertEqual(str(payload.get("email_transport_status") or ""), "failed")
        self.assertIn("SMTP connection blocked", str(payload.get("email_failure_reason_normalized") or ""))


if __name__ == "__main__":
    unittest.main()
