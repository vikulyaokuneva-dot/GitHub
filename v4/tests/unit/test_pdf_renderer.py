from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v4.delivery.pdf.renderer import _display_value_by_status, _mode_notes, _to_render_lines, render_pdf
from v4.outputs.pdf.contracts import PdfBlock, PdfPage, PdfPayload


class TestPdfRenderer(unittest.TestCase):
    def test_render_pdf_creates_file_and_includes_audit_marker(self) -> None:
        payload = PdfPayload(
            mode="audit",
            pages=[
                PdfPage(
                    title="Executive",
                    blocks=[
                        PdfBlock(
                            title="Summary",
                            rows=[
                                {"label": "Metric 1", "value": 10, "status": "confirmed"},
                                {"label": "Metric 2", "value": None, "status": "partial"},
                                {"label": "Metric 3", "value": None, "status": "unavailable"},
                            ],
                            status="partial",
                        )
                    ],
                )
            ],
            warnings=["w1"],
            diagnostics={"pages_count": 1},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = render_pdf(payload, Path(tmpdir) / "report.pdf")
            path = Path(output)

            self.assertTrue(path.exists())
            self.assertEqual(path.suffix.lower(), ".pdf")
            lines = _to_render_lines(payload)
            self.assertTrue(any("audit_file_mode" in line for line in lines))

    def test_status_display_policy(self) -> None:
        self.assertEqual(_display_value_by_status({"value": 100, "status": "confirmed"}), "100")
        self.assertEqual(_display_value_by_status({"value": 100, "status": "partial"}), "частично")
        self.assertEqual(_display_value_by_status({"value": None, "status": "unavailable"}), "нет данных")

    def test_mode_notes_audit_contains_disclaimer(self) -> None:
        payload = PdfPayload(mode="audit")
        notes = _mode_notes(payload)
        self.assertTrue(any("audit_file_mode" in line for line in notes))


if __name__ == "__main__":
    unittest.main()
