import unittest

from src.mailer_yandex import normalize_email_failure_reason


class TestMailerFailureNormalization(unittest.TestCase):
    def test_winerror_10013_normalized(self) -> None:
        err = OSError("[WinError 10013] blocked")
        setattr(err, "winerror", 10013)
        normalized = normalize_email_failure_reason(err)
        self.assertEqual(normalized, "SMTP connection blocked by runtime environment")


if __name__ == "__main__":
    unittest.main()
