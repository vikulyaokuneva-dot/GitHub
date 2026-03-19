from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.scripts.smoke_render_pdf import run_smoke


class TestSmokeRenderPdfScript(unittest.TestCase):
    def test_smoke_render_pdf_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            fake_result = {
                "outputs": {"pdf": object(), "email": object(), "artifacts": {"saved_files": {}}},
            }
            fake_delivery = {
                "pdf_path": str(pdf_path),
                "email_preview_path": None,
                "diagnostics": {"rendered_pdf": True},
            }

            with (
                patch("v4.scripts.smoke_render_pdf.run_daily_pipeline", return_value=fake_result),
                patch("v4.scripts.smoke_render_pdf.run_delivery_stage", return_value=fake_delivery),
            ):
                code = run_smoke(
                    mode="daily",
                    seller_id="seller_001",
                    run_date="2026-03-15",
                    timezone="Europe/Moscow",
                    input_path=None,
                    output_dir=tmpdir,
                    dry_run=True,
                )

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
