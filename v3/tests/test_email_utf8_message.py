import unittest

from src.mailer_yandex import build_email_message


class TestEmailUtf8Message(unittest.TestCase):
    def test_build_message_uses_utf8_for_subject_and_body(self) -> None:
        msg = build_email_message(
            subject="Управленческое резюме: seller_001",
            body="Сегодня финансовый контур не подтвержден.",
            from_addr="robot@example.com",
            to_addr="owner@example.com",
            pdf_bytes=b"%PDF-1.4\n",
            pdf_filename="report.pdf",
        )

        raw = msg.as_bytes()
        self.assertIn(b"Subject: =?utf-8?", raw)

        plain = msg.get_body(preferencelist=("plain",))
        self.assertIsNotNone(plain)
        self.assertEqual(str(plain.get_content_charset() or "").lower(), "utf-8")
        self.assertIn("финансовый контур", str(plain.get_content() or "").lower())


if __name__ == "__main__":
    unittest.main()
