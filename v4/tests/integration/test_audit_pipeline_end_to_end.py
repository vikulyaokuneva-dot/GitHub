from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v4.pipeline.runners.audit_runner import run_audit_pipeline


DAILY_CSV = """Обоснование для оплаты,Кол-во,Дата продажи,Дата заказа покупателем,Цена розничная,Код номенклатуры,Вайлдберриз реализовал Товар (Пр),К перечислению Продавцу за реализованный Товар
Продажа,1,2026-03-15,2026-03-15,100,12345,95,80
"""

AUDIT_DISCLAIMER = "Отчет построен в audit_file_mode; выводы ограничены доступными файлами."


class TestAuditPipelineEndToEnd(unittest.TestCase):
    def test_audit_pipeline_end_to_end_partial_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            (input_dir / "daily_report.csv").write_text(DAILY_CSV, encoding="utf-8")

            result = run_audit_pipeline(
                input_path=str(input_dir),
                run_context={
                    "seller_id": "seller_001",
                    "run_date": "2026-03-15",
                    "timezone": "Europe/Moscow",
                },
                output_dir=None,
            )

        self.assertIn("run_context", result)
        self.assertIn("diagnostics", result)
        self.assertIn("metrics", result)
        self.assertIn("facts", result)
        self.assertIn("decisions", result)
        self.assertIn("outputs", result)
        self.assertIn("warnings", result)

        self.assertIn("job", result["diagnostics"])
        self.assertIn("summary", result["diagnostics"])
        self.assertEqual(result["diagnostics"]["summary"]["mode"], "audit_file_mode")

        self.assertIn("artifacts", result["outputs"])
        self.assertEqual(result["outputs"]["artifacts"]["saved_files"], {})

        email_payload = result["outputs"]["email"]
        self.assertTrue(any(AUDIT_DISCLAIMER in line for line in email_payload.summary_lines))


if __name__ == "__main__":
    unittest.main()
