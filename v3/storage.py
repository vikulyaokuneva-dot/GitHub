from __future__ import annotations
from typing import Any, Dict
from datetime import datetime, timezone
import inspect
import json
import os
import traceback

REPORT_VERSION_ENV = "REPORT_VERSION"
REPORT_VERSION_V2 = "v2"
LEGACY_WRITE_FORBIDDEN_MESSAGE = "LEGACY_JOB_META_WRITE_FORBIDDEN_IN_REPORT_VERSION_V2"

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _json_writer_source(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "legacy"
    report_version = str(payload.get("report_version") or "").strip().lower()
    renderer = str(payload.get("renderer") or "").strip().lower()
    source_of_truth = str(payload.get("source_of_truth") or "").strip().lower()
    artifacts = payload.get("artifacts")
    artifact_pdf = ""
    if isinstance(artifacts, dict):
        artifact_pdf = str(artifacts.get("pdf") or "").strip().lower()
    if (
        report_version == "v2"
        or renderer == "report_v2"
        or source_of_truth == "snapshot.json"
        or artifact_pdf == "report_v2.pdf"
    ):
        return "v2"
    return "legacy"

def _json_writer_payload_summary(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}
    summary: Dict[str, Any] = {}
    for key in (
        "status",
        "error",
        "report_version",
        "renderer",
        "source_of_truth",
        "pdf_source_mode",
        "core_report_payload_available",
        "pdf_path",
        "artifacts",
    ):
        if key in payload:
            summary[key] = payload.get(key)
    return summary

def _json_writer_caller() -> tuple[str, str]:
    caller_frame = None
    for frame_info in inspect.stack()[2:]:
        if os.path.abspath(frame_info.filename) != os.path.abspath(__file__):
            caller_frame = frame_info
            break
    caller_file = os.path.relpath(caller_frame.filename, os.getcwd()) if caller_frame else "<unknown>"
    caller_function = caller_frame.function if caller_frame else "<unknown>"
    return caller_file, caller_function

def _trace_json_writer_before(path: str, payload: Any) -> tuple[bool, str, str, str]:
    filename = os.path.basename(str(path or ""))
    if filename not in {"job.json", "report_meta.json"}:
        return False, "", "", ""
    caller_file, caller_function = _json_writer_caller()
    report_version = ""
    if isinstance(payload, dict):
        report_version = str(payload.get("report_version") or "").strip()
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source = _json_writer_source(payload)
    target_abs = os.path.abspath(path)
    raw_env = os.environ.get(REPORT_VERSION_ENV)
    print(
        "[json_writer_trace] "
        f"file={caller_file} "
        f"function={caller_function} "
        f"source={source} "
        f"timestamp={timestamp} "
        f"env_REPORT_VERSION={raw_env!r} "
        f"report_version={report_version or '<empty>'} "
        f"cwd={os.getcwd()} "
        f"target={path} "
        f"target_abs={target_abs}"
    )
    if str(raw_env or "").strip().lower() == REPORT_VERSION_V2 and source == "legacy":
        print(
            "[json_writer_guard] "
            f"{LEGACY_WRITE_FORBIDDEN_MESSAGE} "
            f"file={caller_file} "
            f"function={caller_function} "
            f"target_abs={target_abs}"
        )
        print("[json_writer_guard_stack]\n" + "".join(traceback.format_stack(limit=30)))
        raise RuntimeError(LEGACY_WRITE_FORBIDDEN_MESSAGE)
    return True, source, caller_file, caller_function

def _trace_json_writer_after(path: str, payload: Any, source: str) -> None:
    filename = os.path.basename(str(path or ""))
    if filename not in {"job.json", "report_meta.json"}:
        return
    target_abs = os.path.abspath(path)
    try:
        stat = os.stat(path)
        mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        size = int(stat.st_size)
    except OSError:
        mtime = "<missing>"
        size = -1
    print(
        "[json_writer_after] "
        f"source={source} "
        f"target_abs={target_abs} "
        f"mtime={mtime} "
        f"size={size}"
    )
    if source == "v2":
        print(
            "[json_writer_after_content] "
            + json.dumps(_json_writer_payload_summary(payload), ensure_ascii=False, sort_keys=True)
        )

def write_json(path: str, payload: Any) -> None:
    ensure_dir(os.path.dirname(path))
    traced, source, _, _ = _trace_json_writer_before(path, payload)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if traced:
        _trace_json_writer_after(path, payload, source)

def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
