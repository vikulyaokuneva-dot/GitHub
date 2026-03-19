from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from v4.core.contracts import RunContext, RunMode
from v4.pipeline.contracts import PipelineRunResult
from v4.pipeline.runners.audit_runner import run_audit_pipeline
from v4.pipeline.runners.daily_runner import run_daily_pipeline


DAILY_CSV = """Обоснование для оплаты,Кол-во,Дата продажи,Дата заказа покупателем,Цена розничная,Код номенклатуры,Вайлдберриз реализовал Товар (Пр),К перечислению Продавцу за реализованный Товар
Продажа,1,2026-03-15,2026-03-15,100,12345,95,80
"""


class TestPipelineResultContract(unittest.TestCase):
    def test_pipeline_result_to_dict_contract(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
        )

        result = PipelineRunResult(
            run_context=context,
            diagnostics={"summary": {"mode": "daily_api_mode"}},
            outputs={"artifacts": {"saved_files": {}}},
            warnings=["w1"],
        ).to_dict()

        self.assertEqual(
            set(result.keys()),
            {"run_context", "diagnostics", "metrics", "facts", "decisions", "outputs", "warnings"},
        )
        self.assertEqual(result["run_context"].mode.value, "daily_api_mode")
        self.assertIsNone(result["metrics"])
        self.assertIsNone(result["facts"])
        self.assertIsNone(result["decisions"])
        self.assertEqual(result["warnings"], ["w1"])

    def test_daily_runner_result_contract(self) -> None:
        with patch.dict("os.environ", {"WB_API_TOKEN": ""}, clear=False):
            result = run_daily_pipeline(
                run_context={
                    "seller_id": "seller_001",
                    "run_date": "2026-03-15",
                    "timezone": "Europe/Moscow",
                },
                output_dir=None,
            )

        self.assertEqual(
            set(result.keys()),
            {"run_context", "diagnostics", "metrics", "facts", "decisions", "outputs", "warnings"},
        )
        self.assertEqual(result["run_context"].mode.value, "daily_api_mode")
        self.assertIn("job", result["diagnostics"])
        self.assertIn("summary", result["diagnostics"])
        self.assertEqual(result["diagnostics"]["summary"]["mode"], "daily_api_mode")

    def test_audit_runner_result_contract(self) -> None:
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

        self.assertEqual(
            set(result.keys()),
            {"run_context", "diagnostics", "metrics", "facts", "decisions", "outputs", "warnings"},
        )
        self.assertEqual(result["run_context"].mode.value, "audit_file_mode")
        self.assertIn("job", result["diagnostics"])
        self.assertIn("summary", result["diagnostics"])
        self.assertEqual(result["diagnostics"]["summary"]["mode"], "audit_file_mode")


if __name__ == "__main__":
    unittest.main()
