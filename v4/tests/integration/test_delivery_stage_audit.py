from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v4.outputs.email.builder import AUDIT_DISCLAIMER
from v4.pipeline.runners.audit_runner import run_audit_pipeline
from v4.pipeline.stages.delivery_stage import run_delivery_stage


DAILY_CSV = """Обоснование для оплаты,Кол-во,Дата продажи,Дата заказа покупателем,Цена розничная,Код номенклатуры,Вайлдберриз реализовал Товар (Пр),К перечислению Продавцу за реализованный Товар
Продажа,1,2026-03-15,2026-03-15,100,12345,95,80
"""


class TestDeliveryStageAudit(unittest.TestCase):
    def test_delivery_stage_audit_writes_pdf_and_preview_with_disclaimer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            out_dir = Path(tmpdir) / "out"
            input_dir.mkdir(parents=True, exist_ok=True)
            out_dir.mkdir(parents=True, exist_ok=True)
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

            delivery = run_delivery_stage(
                outputs=result["outputs"],
                output_dir=str(out_dir),
                enable_pdf_render=True,
                enable_email_preview=True,
            )

            pdf_path = Path(str(delivery["pdf_path"]))
            preview_path = Path(str(delivery["email_preview_path"]))
            self.assertTrue(pdf_path.exists())
            self.assertTrue(preview_path.exists())

            preview = json.loads(preview_path.read_text(encoding="utf-8"))
            self.assertIn(AUDIT_DISCLAIMER, preview["body"])

            diagnostics = delivery["diagnostics"]
            self.assertEqual(diagnostics["mode"], "audit")
            self.assertTrue(diagnostics["rendered_pdf"])
            self.assertTrue(diagnostics["email_preview_built"])


if __name__ == "__main__":
    unittest.main()
