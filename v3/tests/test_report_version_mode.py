import json
import os
import tempfile
import unittest
from unittest.mock import patch

from v3.entry import _finalize_daily_delivery, _run_daily_for_seller
from v3.pipeline.daily_output_stage import run_daily_output_stage


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _snapshot_payload() -> dict:
    return {
        "seller_id": "seller_001",
        "run_date": "2026-04-21",
        "operational_date": "2026-04-21",
        "source_mode": "wb_api_core_v2",
        "cabinet_commerce_daily": {
            "source": "sales_funnel_api",
            "available": True,
            "target_date": "2026-04-21",
            "orders_count": 5.0,
            "orders_amount": 4260.0,
            "buyouts_count": 2.0,
            "buyouts_amount": 1700.0,
        },
        "finance_final_daily": {
            "source": "finance_detailed_api",
            "available": True,
            "target_date": "2026-04-21",
            "actual_date": "2026-04-21",
            "date_aligned": True,
            "gross_revenue": 4652.0,
            "seller_payout": 4868.22,
            "wb_commission": -329.75,
            "logistics": 3.0,
            "storage": 68.37,
            "acquiring": 186.08,
        },
        "live_operational": {
            "orders": {
                "source": "orders_api",
                "available": True,
                "target_date": "2026-04-21",
                "count": 3.0,
                "amount": 2500.0,
            },
            "sales": {
                "source": "sales_api",
                "available": True,
                "target_date": "2026-04-21",
                "count": 3.0,
                "amount": 7160.0,
            },
            "stocks": {
                "source": "stocks_api",
                "available": True,
                "snapshot_kind": "live_snapshot",
                "operational_date_reference": "2026-04-21",
                "snapshot_date": "2026-04-22",
                "total_units": 322.0,
            },
        },
    }


def _debug_payload() -> dict:
    return {
        "warnings": [],
        "endpoints": {
            "cabinet_commerce": {},
            "finance_final": {},
            "orders": {},
            "sales": {},
            "stocks": {},
        },
    }


class TestReportVersionMode(unittest.TestCase):
    def test_daily_output_stage_v2_mode_uses_report_v2_and_writes_meta(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            out_dir = os.path.join(repo_root, "cabinets", "seller_001", "artifacts")
            core_dir = os.path.join(out_dir, "wb_api_core", "2026-04-21")
            _write_json(os.path.join(core_dir, "snapshot.json"), _snapshot_payload())
            _write_json(os.path.join(core_dir, "debug.json"), _debug_payload())

            with patch.dict(os.environ, {"REPORT_VERSION": "v2"}, clear=False):
                with patch(
                    "v3.pipeline.daily_output_stage.run_daily_email_stage",
                    side_effect=AssertionError("legacy email stage should not run in report_v2 mode"),
                ), patch(
                    "v3.pipeline.daily_output_stage.run_daily_report_stage",
                    side_effect=AssertionError("legacy report stage should not run in report_v2 mode"),
                ), patch(
                    "v3.pipeline.daily_output_stage.run_daily_history_stage",
                    side_effect=AssertionError("history stage should not run in report_v2 mode"),
                ):
                    result = run_daily_output_stage(
                        {
                            "repo_root": repo_root,
                            "seller_id": "seller_001",
                            "run_date": "2026-04-21",
                            "out_dir": out_dir,
                            "started_at": "2026-04-21T10:00:00Z",
                        }
                    )

            self.assertEqual(result.get("report_version"), "v2")
            self.assertEqual(result.get("renderer"), "report_v2")
            self.assertEqual(result.get("source_of_truth"), "snapshot.json")
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "report_v2.pdf")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "report_payload_v2.json")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "email_v2.html")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "email_v2.txt")))
            self.assertTrue(os.path.isfile(os.path.join(out_dir, "report_meta.json")))

            with open(os.path.join(out_dir, "report_meta.json"), "r", encoding="utf-8-sig") as file:
                report_meta = json.load(file)
            expected_artifacts = {
                "pdf": "report_v2.pdf",
                "payload": "report_payload_v2.json",
                "email_html": "email_v2.html",
                "email_txt": "email_v2.txt",
            }
            self.assertEqual(report_meta.get("report_version"), "v2")
            self.assertEqual(report_meta.get("renderer"), "report_v2")
            self.assertEqual(report_meta.get("source_of_truth"), "snapshot.json")
            self.assertEqual(report_meta.get("status"), "success")
            self.assertEqual(report_meta.get("artifacts"), expected_artifacts)

    def test_daily_output_stage_v2_mode_writes_job_with_only_v2_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            out_dir = os.path.join(repo_root, "cabinets", "seller_001", "artifacts")
            core_dir = os.path.join(out_dir, "wb_api_core", "2026-04-21")
            _write_json(os.path.join(core_dir, "snapshot.json"), _snapshot_payload())
            _write_json(os.path.join(core_dir, "debug.json"), _debug_payload())

            with patch.dict(os.environ, {"REPORT_VERSION": "v2"}, clear=False):
                result = run_daily_output_stage(
                    {
                        "repo_root": repo_root,
                        "seller_id": "seller_001",
                        "run_date": "2026-04-21",
                        "out_dir": out_dir,
                        "started_at": "2026-04-21T10:00:00Z",
                    }
                )

            with open(os.path.join(out_dir, "job.json"), "r", encoding="utf-8-sig") as file:
                job = json.load(file)

            expected_artifacts = {
                "pdf": "report_v2.pdf",
                "payload": "report_payload_v2.json",
                "email_html": "email_v2.html",
                "email_txt": "email_v2.txt",
            }
            self.assertEqual(result.get("report_version"), "v2")
            self.assertEqual(result.get("status"), "success")
            self.assertEqual(job.get("report_version"), "v2")
            self.assertEqual(job.get("status"), "success")
            self.assertEqual(job.get("renderer"), "report_v2")
            self.assertEqual(job.get("source_of_truth"), "snapshot.json")
            self.assertEqual(job.get("artifacts"), expected_artifacts)
            self.assertEqual(os.path.basename(str(job.get("pdf_path") or "")), "report_v2.pdf")
            self.assertNotIn("report.pdf", json.dumps(job, ensure_ascii=False))

    def test_daily_output_stage_v2_env_overrides_legacy_context_mode(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            out_dir = os.path.join(repo_root, "cabinets", "seller_001", "artifacts")
            core_dir = os.path.join(out_dir, "wb_api_core", "2026-04-21")
            _write_json(os.path.join(core_dir, "snapshot.json"), _snapshot_payload())
            _write_json(os.path.join(core_dir, "debug.json"), _debug_payload())

            with patch.dict(os.environ, {"REPORT_VERSION": "v2"}, clear=False):
                with patch(
                    "v3.pipeline.daily_output_stage.run_daily_report_stage",
                    side_effect=AssertionError("legacy report stage should not run when env REPORT_VERSION=v2"),
                ), patch(
                    "v3.pipeline.daily_output_stage.run_daily_email_stage",
                    side_effect=AssertionError("legacy email stage should not run when env REPORT_VERSION=v2"),
                ):
                    result = run_daily_output_stage(
                        {
                            "repo_root": repo_root,
                            "seller_id": "seller_001",
                            "run_date": "2026-04-21",
                            "out_dir": out_dir,
                            "started_at": "2026-04-21T10:00:00Z",
                            "report_version": "legacy",
                        }
                    )

            self.assertEqual(result.get("report_version"), "v2")
            self.assertEqual(result.get("status"), "success")
            with open(os.path.join(out_dir, "report_meta.json"), "r", encoding="utf-8-sig") as file:
                report_meta = json.load(file)
            self.assertNotEqual(report_meta.get("pdf_source_mode"), "legacy")

    def test_entry_v2_full_run_keeps_v2_result_over_legacy_context(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            out_dir = os.path.join(repo_root, "cabinets", "seller_001", "artifacts")
            input_dir = os.path.join(repo_root, "cabinets", "seller_001", "input")
            core_dir = os.path.join(out_dir, "wb_api_core", "2026-04-21")
            os.makedirs(input_dir, exist_ok=True)
            _write_json(os.path.join(core_dir, "snapshot.json"), _snapshot_payload())
            _write_json(os.path.join(core_dir, "debug.json"), _debug_payload())
            with open(os.path.join(out_dir, "report.pdf"), "wb") as file:
                file.write(b"legacy pdf")

            base_context = {
                "repo_root": repo_root,
                "seller_id": "seller_001",
                "run_date": "2026-04-21",
                "seller_input_dir": input_dir,
                "out_dir": out_dir,
                "started_at": "2026-04-21T10:00:00Z",
                "discovered_files": {},
                "api_debug": {},
                "report_version": "legacy",
            }
            legacy_context = dict(base_context)
            legacy_context.update(
                {
                    "status": "partial_success",
                    "error": "данные о продажах не получены",
                    "job": {
                        "status": "partial_success",
                        "error": "данные о продажах не получены",
                        "artifacts": ["job.json", "report.pdf"],
                    },
                }
            )

            with patch.dict(os.environ, {"REPORT_VERSION": "v2"}, clear=False):
                with patch(
                    "v3.pipeline.daily_input_stage.run_daily_input_stage",
                    return_value=base_context,
                ), patch("v3.entry._parse_local_daily_payload", return_value={}), patch(
                    "v3.entry._parse_local_funnel_payload",
                    return_value={},
                ), patch(
                    "v3.entry.build_metrics",
                    return_value=base_context,
                ), patch(
                    "v3.pipeline.daily_ai_stage.run_daily_ai_stage",
                    return_value=legacy_context,
                ), patch(
                    "v3.entry.orchestrate_daily_email_send",
                    side_effect=AssertionError("legacy email send should not run for report_v2"),
                ):
                    result = _run_daily_for_seller(repo_root, "seller_001", "2026-04-21")
                    result = _finalize_daily_delivery(result, seller_id="seller_001", run_date="2026-04-21")

            with open(os.path.join(out_dir, "job.json"), "r", encoding="utf-8-sig") as file:
                job = json.load(file)
            with open(os.path.join(out_dir, "report_meta.json"), "r", encoding="utf-8-sig") as file:
                report_meta = json.load(file)

            self.assertEqual(result.get("status"), "success")
            self.assertIsNone(result.get("error"))
            self.assertEqual(job.get("status"), "success")
            self.assertIsNone(job.get("error"))
            self.assertEqual(job.get("report_version"), "v2")
            self.assertEqual(report_meta.get("report_version"), "v2")
            self.assertEqual(job.get("artifacts", {}).get("pdf"), "report_v2.pdf")
            self.assertNotIn("report.pdf", json.dumps(job, ensure_ascii=False))

    def test_daily_output_stage_legacy_mode_keeps_legacy_chain(self) -> None:
        with patch.dict(os.environ, {"REPORT_VERSION": "legacy"}, clear=False):
            with patch(
                "v3.pipeline.daily_output_stage.prepare_daily_output_payload",
                return_value={"step": "prepared"},
            ) as prepare_mock, patch(
                "v3.pipeline.daily_output_stage.run_daily_email_stage",
                return_value={"step": "email"},
            ) as email_mock, patch(
                "v3.pipeline.daily_output_stage.run_daily_report_stage",
                return_value={"step": "report"},
            ) as report_mock, patch(
                "v3.pipeline.daily_output_stage.run_daily_history_stage",
                return_value={"status": "success", "artifacts_dir": "tmp"},
            ) as history_mock, patch(
                "v3.pipeline.daily_output_stage.build_report_v2_from_files",
                side_effect=AssertionError("report_v2 should not run in legacy mode"),
            ):
                result = run_daily_output_stage({"seller_id": "seller_001"})

        prepare_mock.assert_called_once()
        email_mock.assert_called_once()
        report_mock.assert_called_once()
        history_mock.assert_called_once()
        self.assertEqual(result.get("status"), "success")

    def test_finalize_daily_delivery_skips_legacy_finalize_writers_for_v2(self) -> None:
        with patch(
            "v3.entry.orchestrate_daily_email_send",
            side_effect=AssertionError("legacy email send should not run for report_v2"),
        ), patch("v3.entry.persist_result_job_if_possible") as persist_mock:
            result = _finalize_daily_delivery(
                {
                    "status": "success",
                    "report_version": "v2",
                    "artifacts_dir": os.getcwd(),
                },
                seller_id="seller_001",
                run_date="2026-04-21",
            )

        persist_mock.assert_not_called()
        self.assertEqual(result.get("report_version"), "v2")

    def test_finalize_daily_delivery_uses_legacy_email_send_for_legacy_mode(self) -> None:
        legacy_result = {
            "status": "success",
            "artifacts_dir": os.getcwd(),
            "email_summary": {},
        }
        finalized_result = dict(legacy_result)
        finalized_result["email_transport_status"] = "success"

        with patch(
            "v3.entry.orchestrate_daily_email_send",
            return_value=finalized_result,
        ) as send_mock, patch("v3.entry.persist_result_job_if_possible") as persist_mock:
            result = _finalize_daily_delivery(
                legacy_result,
                seller_id="seller_001",
                run_date="2026-04-21",
            )

        send_mock.assert_called_once()
        persist_mock.assert_called_once()
        self.assertEqual(result.get("email_transport_status"), "success")


if __name__ == "__main__":
    unittest.main()
