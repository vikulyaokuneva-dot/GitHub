from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v4.outputs.email.builder import AUDIT_DISCLAIMER
from v4.pipeline.runners.audit_runner import run_audit_pipeline


DAILY_CSV = """Обоснование для оплаты,Кол-во,Дата продажи,Дата заказа покупателем,Цена розничная,Код номенклатуры,Вайлдберриз реализовал Товар (Пр),К перечислению Продавцу за реализованный Товар
Продажа,1,2026-03-15,2026-03-15,100,12345,95,80
"""


class TestAuditOutputSnapshots(unittest.TestCase):
    def test_audit_output_structure_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "input"
            output_dir = root / "audit_out"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            (input_dir / "daily_report.csv").write_text(DAILY_CSV, encoding="utf-8")

            result = run_audit_pipeline(
                input_path=str(input_dir),
                run_context={
                    "seller_id": "seller_001",
                    "run_date": "2026-03-15",
                    "timezone": "Europe/Moscow",
                },
                output_dir=str(output_dir),
            )

            self.assertEqual(set(result.keys()), {"run_context", "diagnostics", "metrics", "facts", "decisions", "outputs", "warnings"})
            self.assertEqual(result["run_context"].mode.value, "audit_file_mode")

            diagnostics = result["diagnostics"]
            self.assertIn("job", diagnostics)
            self.assertIn("summary", diagnostics)
            summary = diagnostics["summary"]
            self.assertEqual(summary["mode"], "audit_file_mode")
            self.assertIn("files_detected_count", summary)
            self.assertIn("files_missing_expected", summary)
            self.assertEqual(summary["input_path_label"], "input")
            self.assertEqual(set(summary["decision_counts_by_priority"].keys()), {"P1", "P2", "P3"})

            outputs = result["outputs"]
            artifacts = outputs["artifacts"]
            saved_files = artifacts["saved_files"]
            self.assertEqual(set(saved_files.keys()), {"facts", "decisions", "outputs_summary"})

            for saved_path in saved_files.values():
                path = Path(saved_path)
                self.assertTrue(path.exists())
                path.resolve().relative_to(output_dir.resolve())

            facts_payload = json.loads(Path(saved_files["facts"]).read_text(encoding="utf-8"))
            decisions_payload = json.loads(Path(saved_files["decisions"]).read_text(encoding="utf-8"))
            outputs_summary = json.loads(Path(saved_files["outputs_summary"]).read_text(encoding="utf-8"))

            self.assertEqual(facts_payload["run_context"]["mode"], "audit_file_mode")
            self.assertEqual(decisions_payload["run_context"]["mode"], "audit_file_mode")
            self.assertEqual(outputs_summary["mode"], "audit")
            self.assertEqual(outputs_summary["audit_note"], AUDIT_DISCLAIMER)
            self.assertEqual(set(outputs_summary["decision_counts_by_priority"].keys()), {"P1", "P2", "P3"})

            email_payload = outputs["email"]
            pdf_payload = outputs["pdf"]
            self.assertEqual(email_payload.mode, "audit")
            self.assertTrue(any(AUDIT_DISCLAIMER in line for line in email_payload.summary_lines))
            self.assertEqual(pdf_payload.mode, "audit")
            self.assertTrue(pdf_payload.diagnostics["audit_disclaimer_included"])


if __name__ == "__main__":
    unittest.main()
