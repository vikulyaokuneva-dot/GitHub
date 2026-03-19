from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v4.delivery.email.sender import build_email_message, save_email_preview
from v4.outputs.email.contracts import EmailPayload, EmailSection


class TestEmailSenderContract(unittest.TestCase):
    def _payload(self) -> EmailPayload:
        return EmailPayload(
            subject="subject",
            preheader="preheader",
            mode="daily",
            summary_lines=["summary"],
            sections=[EmailSection(title="S1", lines=["l1"], status="confirmed")],
            warnings=["w1"],
        )

    def test_build_email_message_contract(self) -> None:
        payload = self._payload()
        message = build_email_message(payload, attachments=["a.pdf", "a.pdf", "b.pdf"])

        self.assertEqual(message["subject"], "subject")
        self.assertEqual(message["preheader"], "preheader")
        self.assertEqual(message["mode"], "daily")
        self.assertEqual(message["attachments"], ["a.pdf", "b.pdf"])
        self.assertIn("Subject: subject", message["body"])

    def test_save_email_preview_file(self) -> None:
        payload = self._payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            preview_path = save_email_preview(payload, tmpdir, attachments=["report.pdf"])
            path = Path(preview_path)

            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["subject"], "subject")
            self.assertEqual(loaded["attachments"], ["report.pdf"])
            self.assertIn("body", loaded)

    def test_save_email_preview_requires_output_dir(self) -> None:
        payload = self._payload()
        with self.assertRaises(ValueError):
            save_email_preview(payload, None)


if __name__ == "__main__":
    unittest.main()
