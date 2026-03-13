import os
import tempfile
import unittest

from v3.pdf_render import normalize_pdf_text, repair_mojibake, write_text_pdf


class TestPdfTextEncoding(unittest.TestCase):
    def test_russian_text_is_not_modified(self) -> None:
        text = "Управленческий отчет"
        self.assertEqual(repair_mojibake(text), text)
        self.assertEqual(normalize_pdf_text(text), text)

    def test_english_text_is_not_modified(self) -> None:
        text = "seller_001 orders buyouts"
        self.assertEqual(repair_mojibake(text), text)
        self.assertEqual(normalize_pdf_text(text), text)

    def test_repairs_cp1251_mojibake(self) -> None:
        original = "проблема карточки"
        mojibake = original.encode("utf-8").decode("cp1251")
        self.assertNotEqual(mojibake, original)
        self.assertEqual(repair_mojibake(mojibake), original)

    def test_repairs_latin1_mojibake(self) -> None:
        original = "проблема рекламы"
        mojibake = original.encode("utf-8").decode("latin1")
        self.assertNotEqual(mojibake, original)
        self.assertEqual(repair_mojibake(mojibake), original)

    def test_write_text_pdf_accepts_cyrillic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "report.pdf")
            source = "Управленческий отчет"
            mojibake = source.encode("utf-8").decode("cp1251")
            try:
                font_info = write_text_pdf(
                    path,
                    [
                        "# " + mojibake,
                        "кабинет seller_001",
                        "надежность AI",
                        "не подтверждено",
                        "заказы",
                        "выкупы",
                        "проблема карточки",
                        "проблема рекламы",
                    ],
                )
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(str(font_info.get("family") or "").strip())


if __name__ == "__main__":
    unittest.main()
