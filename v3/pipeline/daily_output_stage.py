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

V2_ARTIFACT_FILENAMES = {
    "pdf": "report_v2.pdf",
    "payload": "report_payload_v2.json",
    "email_html": "email_v2.html",
    "email_txt": "email_v2.txt",
}


def _resolve_report_version(context: Dict[str, Any]) -> str:
    raw_context_value = context.get("report_version") if isinstance(context, dict) else None
    raw_env_value = os.getenv(REPORT_VERSION_ENV, "")
    explicit_mode = str(raw_env_value or raw_context_value or "").strip().lower()
    return REPORT_VERSION_V2 if explicit_mode == REPORT_VERSION_V2 else REPORT_VERSION_LEGACY


def _path_mtime(path: str | Path) -> str:
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except OSError:
        return "<missing>"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _v2_artifact_registry() -> Dict[str, str]:
    return dict(V2_ARTIFACT_FILENAMES)


def _require_v2_output_files(report_v2_result: Dict[str, Any]) -> None:
    required_path_keys = ("payload_path", "pdf_path", "email_html_path", "email_txt_path")
    missing = [
        str(report_v2_result.get(key) or "")
        for key in required_path_keys
        if not str(report_v2_result.get(key) or "").strip()
        or not os.path.isfile(str(report_v2_result.get(key) or ""))
    ]
    if missing:
        raise FileNotFoundError("report_v2_required_outputs_missing: " + ", ".join(missing))


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
    print(
        "[daily_output_stage] v2 output stage start "
        f"cwd={os.getcwd()} "
        f"repo_root={repo_root} "
        f"repo_root_abs={os.path.abspath(repo_root)} "
        f"out_dir={out_dir} "
        f"out_dir_abs={os.path.abspath(out_dir)} "
        f"snapshot_path={snapshot_paths['snapshot_path']} "
        f"snapshot_mtime={_path_mtime(snapshot_paths['snapshot_path'])}"
    )
    report_v2_result = build_report_v2_from_files(
        snapshot_path=snapshot_paths["snapshot_path"],
        debug_path=snapshot_paths["debug_path"],
        out_dir=out_dir,
        payload_path=Path(out_dir) / "report_payload_v2.json",
        pdf_path=Path(out_dir) / "report_v2.pdf",
    )
    _require_v2_output_files(report_v2_result if isinstance(report_v2_result, dict) else {})

    report_payload = report_v2_result.get("payload", {}) if isinstance(report_v2_result, dict) else {}
    if not isinstance(report_payload, dict):
        report_payload = {}
    meta = report_payload.get("meta", {}) if isinstance(report_payload.get("meta"), dict) else {}
    warnings = report_payload.get("warnings", []) if isinstance(report_payload.get("warnings"), list) else []

    source_mode = str(meta.get("snapshot_source_mode") or "wb_api_core_v2")
    report_date = str(meta.get("report_date") or run_date)
    operational_day = str(meta.get("operational_date") or report_date)
    normalized_seller_id = str(meta.get("seller_id") or seller_id)
    artifacts_registry = _v2_artifact_registry()

    report_meta: Dict[str, Any] = {
        "seller_id": normalized_seller_id,
        "report_date": report_date,
        "operational_day": operational_day,
        "source_mode": source_mode,
        "status": "success",
        "report_version": REPORT_VERSION_V2,
        "renderer": "report_v2",
        "source_of_truth": "snapshot.json",
        "artifacts": artifacts_registry,
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
            "artifacts": artifacts_registry,
            "report_meta": report_meta,
            "payload_path": str(report_v2_result.get("payload_path") or ""),
            "pdf_path": str(report_v2_result.get("pdf_path") or ""),
            "email_html_path": str(report_v2_result.get("email_html_path") or ""),
            "email_txt_path": str(report_v2_result.get("email_txt_path") or ""),
            "report_meta_path": str(Path(out_dir) / "report_meta.json"),
            "artifacts_dir": out_dir,
        }
    )
    print(
        "[daily_output_stage] v2 output result "
        f"status={result.get('status')} "
        f"pdf_path={result.get('pdf_path')} "
        f"artifacts={result.get('artifacts')}"
    )
    write_job(out_dir=out_dir, job=result)
    print(
        "[daily_output_stage] v2 output stage end "
        f"job_path={Path(out_dir) / 'job.json'} "
        f"job_mtime={_path_mtime(Path(out_dir) / 'job.json')} "
        f"report_meta_path={Path(out_dir) / 'report_meta.json'} "
        f"report_meta_mtime={_path_mtime(Path(out_dir) / 'report_meta.json')}"
    )
    return result


def run_daily_output_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    report_version = _resolve_report_version(context)
    raw_context_value = context.get("report_version") if isinstance(context, dict) else None
    raw_env_value = os.getenv(REPORT_VERSION_ENV)
    print(
        "[daily_output_stage] REPORT_VERSION "
        f"raw_env={raw_env_value!r} "
        f"context={raw_context_value!r} "
        f"resolved={report_version}"
    )
    print(f"[daily_output_stage] branch selected={report_version}")
    if report_version == REPORT_VERSION_V2:
        return _run_daily_output_stage_v2(context)
    print("[daily_output_stage] legacy output stage start")
    payload = prepare_daily_output_payload(context)
    payload = run_daily_email_stage(payload)
    payload = run_daily_report_stage(payload)
    result = run_daily_history_stage(payload)
    print("[daily_output_stage] legacy output stage end")
    return result
