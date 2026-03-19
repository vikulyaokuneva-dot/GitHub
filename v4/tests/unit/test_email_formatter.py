from __future__ import annotations

import unittest

from v4.delivery.email.formatter import format_email_body
from v4.outputs.email.builder import AUDIT_DISCLAIMER
from v4.outputs.email.contracts import EmailPayload, EmailSection


class TestEmailFormatter(unittest.TestCase):
    def _payload(self, mode: str) -> EmailPayload:
        return EmailPayload(
            subject=f"subject {mode}",
            preheader="preheader",
            mode=mode,
            summary_lines=["line1", "line2"],
            sections=[
                EmailSection(title="Section A", lines=["a1", "a2"], status="confirmed"),
                EmailSection(title="Section B", lines=["b1"], status="partial"),
            ],
            warnings=["w1"],
        )

    def test_format_daily_body(self) -> None:
        body = format_email_body(self._payload("daily"))

        self.assertIn("Subject: subject daily", body)
        self.assertIn("Preheader: preheader", body)
        self.assertIn("Summary:", body)
        self.assertIn("[confirmed] Section A", body)
        self.assertIn("[partial] Section B", body)
        self.assertIn("Warnings:", body)
        self.assertIn("- w1", body)
        self.assertNotIn(AUDIT_DISCLAIMER, body)

    def test_format_audit_body_contains_disclaimer(self) -> None:
        body = format_email_body(self._payload("audit"))
        self.assertIn(AUDIT_DISCLAIMER, body)


if __name__ == "__main__":
    unittest.main()
