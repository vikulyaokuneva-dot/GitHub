from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.pipeline.runners.daily_runner import run_daily_pipeline
from v4.pipeline.stages.delivery_stage import run_delivery_stage


class TestDeliveryStageDaily(unittest.TestCase):
    def test_delivery_stage_daily_writes_pdf_and_email_preview(self) -> None:
        with patch.dict(os.environ, {"WB_API_TOKEN": ""}, clear=False):
            result = run_daily_pipeline(
                run_context={
                    "seller_id": "seller_001",
                    "run_date": "2026-03-15",
                    "timezone": "Europe/Moscow",
                },
                output_dir=None,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            delivery = run_delivery_stage(
                outputs=result["outputs"],
                output_dir=tmpdir,
                enable_pdf_render=True,
                enable_email_preview=True,
            )

            pdf_path = Path(str(delivery["pdf_path"]))
            preview_path = Path(str(delivery["email_preview_path"]))

            self.assertTrue(pdf_path.exists())
            self.assertTrue(preview_path.exists())
            pdf_path.resolve().relative_to(Path(tmpdir).resolve())
            preview_path.resolve().relative_to(Path(tmpdir).resolve())

            preview = json.loads(preview_path.read_text(encoding="utf-8"))
            self.assertEqual(preview["mode"], "daily")
            self.assertIn(str(pdf_path), preview["attachments"])

            diagnostics = delivery["diagnostics"]
            self.assertTrue(diagnostics["rendered_pdf"])
            self.assertTrue(diagnostics["email_preview_built"])


if __name__ == "__main__":
    unittest.main()
