from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from report_v2.run_report_v2 import build_report_v2_from_files

from ..core_report_bridge import resolve_core_snapshot_paths
from ..outputs.artifact_writer import write_job, write_report_meta
from ..outputs.daily_artifacts_stage import prepare_daily_output_payload
from ..outputs.daily_email_stage import run_daily_email_stage
from ..outputs.daily_history_stage import run_daily_history_stage
from ..outputs.daily_report_stage import run_daily_report_stage
from .run_summary_builder import build_run_summary


REPORT_VERSION_ENV = "REPORT_VERSION"
REPORT_VERSION_LEGACY = "legacy"
REPORT_VERSION_V2 = "v2"


def _resolve_report_version(context: Dict[str, Any]) -> str:
    raw_context_value = context.get("report_version") if isinstance(context, dict) else None
    raw_env_value = os.getenv(REPORT_VERSION_ENV, "")
    explicit_mode = str(raw_context_value or raw_env_value or "").strip().lower()
    return REPORT_VERSION_V2 if explicit_mode == REPORT_VERSION_V2 else REPORT_VERSION_LEGACY


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_daily_output_stage_v2(context: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = dict(context or {})
    repo_root = str(payload.get("repo_root") or "").strip()
    seller_id = str(payload.get("seller_id") or "").strip()
    run_date = str(payload.get("run_date") or "").strip()
    out_dir = str(payload.get("out_dir") or "").strip()
    started_at = str(payload.get("started_at") or "")

    if not repo_root or not seller_id or not run_date:
        raise ValueError("report_v2_mode_requires_repo_root_seller_id_run_date")
    if not out_dir:
        raise ValueError("report_v2_mode_requires_out_dir")

    snapshot_paths = resolve_core_snapshot_paths(repo_root=repo_root, seller_id=seller_id, run_date=run_date)
    report_v2_result = build_report_v2_from_files(
        snapshot_path=snapshot_paths["snapshot_path"],
        debug_path=snapshot_paths["debug_path"],
        out_dir=out_dir,
        payload_path=Path(out_dir) / "report_payload_v2.json",
        pdf_path=Path(out_dir) / "report_v2.pdf",
    )

    report_payload = report_v2_result.get("payload", {}) if isinstance(report_v2_result, dict) else {}
    if not isinstance(report_payload, dict):
        report_payload = {}
    meta = report_payload.get("meta", {}) if isinstance(report_payload.get("meta"), dict) else {}
    warnings = report_payload.get("warnings", []) if isinstance(report_payload.get("warnings"), list) else []

    source_mode = str(meta.get("snapshot_source_mode") or "wb_api_core_v2")
    report_date = str(meta.get("report_date") or run_date)
    operational_day = str(meta.get("operational_date") or report_date)
    normalized_seller_id = str(meta.get("seller_id") or seller_id)

    report_meta: Dict[str, Any] = {
        "seller_id": normalized_seller_id,
        "report_date": report_date,
        "operational_day": operational_day,
        "source_mode": source_mode,
        "report_version": REPORT_VERSION_V2,
        "renderer": "report_v2",
        "source_of_truth": "snapshot.json",
        "snapshot_path": snapshot_paths["snapshot_path"],
        "debug_path": snapshot_paths["debug_path"] if os.path.isfile(snapshot_paths["debug_path"]) else "",
        "report_payload_path": str(report_v2_result.get("payload_path") or ""),
        "pdf_path": str(report_v2_result.get("pdf_path") or ""),
        "email_html_path": str(report_v2_result.get("email_html_path") or ""),
        "email_txt_path": str(report_v2_result.get("email_txt_path") or ""),
        "warnings": warnings,
        "warnings_count": len(warnings),
    }
    write_report_meta(out_dir=out_dir, report_meta=report_meta)

    result = build_run_summary(
        seller_id=normalized_seller_id,
        mode="daily",
        run_date=report_date,
        started_at=started_at,
        finished_at=_utc_now_iso(),
        source_mode=source_mode,
        artifacts_dir=out_dir,
        status="success",
        artifacts=[
            "report_payload_v2.json",
            "report_v2.pdf",
            "email_v2.html",
            "email_v2.txt",
            "report_meta.json",
        ],
        email_attempted=False,
        email_sent=False,
        email_to="",
        email_error=None,
        email_stage="skipped",
        email_transport_status="skipped",
        email_failure_reason_normalized="",
    )
    result.update(
        {
            "report_version": REPORT_VERSION_V2,
            "renderer": "report_v2",
            "source_of_truth": "snapshot.json",
            "report_meta": report_meta,
            "payload_path": str(report_v2_result.get("payload_path") or ""),
            "pdf_path": str(report_v2_result.get("pdf_path") or ""),
            "email_html_path": str(report_v2_result.get("email_html_path") or ""),
            "email_txt_path": str(report_v2_result.get("email_txt_path") or ""),
            "artifacts_dir": out_dir,
        }
    )
    write_job(out_dir=out_dir, job=result)
    return result


def run_daily_output_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    if _resolve_report_version(context) == REPORT_VERSION_V2:
        return _run_daily_output_stage_v2(context)
    payload = prepare_daily_output_payload(context)
    payload = run_daily_email_stage(payload)
    payload = run_daily_report_stage(payload)
    return run_daily_history_stage(payload)
