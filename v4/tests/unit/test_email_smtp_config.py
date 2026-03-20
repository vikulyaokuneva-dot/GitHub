from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.delivery.email.sender import _resolve_email_config, send_email_via_smtp
from v4.outputs.email.contracts import EmailPayload, EmailSection


class TestEmailSmtpConfig(unittest.TestCase):
    def _payload(self) -> EmailPayload:
        return EmailPayload(
            subject="subject",
            preheader="preheader",
            mode="daily",
            summary_lines=["summary"],
            sections=[EmailSection(title="section", lines=["line"], status="confirmed")],
        )

    def test_config_infers_host_from_username_domain_when_smtp_host_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EMAIL_USERNAME": "bot@mail.ru",
                "EMAIL_PASSWORD": "pwd",
                "EMAIL_TO": "to@example.com",
                "SMTP_HOST": "",
                "SMTP_PORT": "",
                "SMTP_SSL": "",
                "YANDEX_SMTP_HOST": "",
                "YANDEX_SMTP_PORT": "",
            },
            clear=False,
        ):
            cfg = _resolve_email_config()

        self.assertEqual(cfg["smtp_host"], "smtp.mail.ru")
        self.assertEqual(cfg["smtp_port"], 465)
        self.assertTrue(cfg["use_ssl"])
        self.assertEqual(cfg["smtp_host_source"], "inferred_from_email_domain:mail.ru")

    def test_config_infers_outlook_port_and_starttls(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EMAIL_USERNAME": "bot@outlook.com",
                "EMAIL_PASSWORD": "pwd",
                "EMAIL_TO": "to@example.com",
                "SMTP_HOST": "",
                "SMTP_PORT": "",
                "SMTP_SSL": "",
                "YANDEX_SMTP_HOST": "",
                "YANDEX_SMTP_PORT": "",
            },
            clear=False,
        ):
            cfg = _resolve_email_config()

        self.assertEqual(cfg["smtp_host"], "smtp-mail.outlook.com")
        self.assertEqual(cfg["smtp_port"], 587)
        self.assertFalse(cfg["use_ssl"])
        self.assertEqual(cfg["smtp_host_source"], "inferred_from_email_domain:outlook.com")

    def test_send_email_failure_contains_transport_context(self) -> None:
        payload = self._payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            attachment = Path(tmpdir) / "report.txt"
            attachment.write_text("report", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "EMAIL_USERNAME": "bot@mail.ru",
                    "EMAIL_PASSWORD": "pwd",
                    "EMAIL_TO": "to@example.com",
                    "SMTP_HOST": "",
                    "SMTP_PORT": "",
                    "SMTP_SSL": "",
                    "YANDEX_SMTP_HOST": "",
                    "YANDEX_SMTP_PORT": "",
                },
                clear=False,
            ):
                with patch("v4.delivery.email.sender.smtplib.SMTP_SSL", side_effect=OSError("dns failed")):
                    with self.assertRaisesRegex(RuntimeError, "host=smtp.mail.ru"):
                        send_email_via_smtp(payload, attachments=[str(attachment)])


if __name__ == "__main__":
    unittest.main()
