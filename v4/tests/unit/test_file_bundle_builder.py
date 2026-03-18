from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v4.core.contracts import RunContext, RunMode, SourceStatusCode
from v4.ingestion.files.bundle import build_file_raw_bundle


DAILY_CSV = """Обоснование для оплаты,Кол-во,Дата продажи,Дата заказа покупателем,Цена розничная,Код номенклатуры,Вайлдберриз реализовал Товар (Пр),К перечислению Продавцу за реализованный Товар
Продажа,2,2026-03-15,2026-03-15,1200,10001,1100,900
"""


class TestFileBundleBuilder(unittest.TestCase):
    def _context(self) -> RunContext:
        return RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.AUDIT_FILE,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
            dry_run=True,
        )

    def test_bundle_builds_from_available_files_and_marks_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir)
            (input_dir / "daily_report.csv").write_text(DAILY_CSV, encoding="utf-8")

            result = build_file_raw_bundle(input_dir, self._context())

        self.assertIn("realization", result.source_flags)
        self.assertEqual(result.source_flags["realization"], SourceStatusCode.OK)
        self.assertEqual(result.source_flags["funnel"], SourceStatusCode.MISSING)
        self.assertEqual(result.source_flags["ads"], SourceStatusCode.MISSING)

        diagnostics = result.raw_bundle.diagnostics
        self.assertIn("daily_report", diagnostics["detected_files"])
        self.assertIn("funnel_report", diagnostics["missing_expected_files"])
        self.assertIn("ads_report", diagnostics["missing_expected_files"])

    def test_missing_values_not_converted_to_zero_in_default_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir)
            (input_dir / "daily_report.csv").write_text(DAILY_CSV, encoding="utf-8")

            result = build_file_raw_bundle(input_dir, self._context())

        ads_payload = result.raw_bundle.sources["ads"].payload
        self.assertIsInstance(ads_payload, dict)
        self.assertEqual(ads_payload["campaigns"]["raw"], [])
        self.assertEqual(ads_payload["stats"]["rows"], [])
        self.assertNotIn(0, ads_payload["campaigns"]["raw"])


if __name__ == "__main__":
    unittest.main()
