from __future__ import annotations
from typing import Any, Dict
from datetime import datetime, timezone
import inspect
import json
import os

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

def _trace_json_writer(path: str, payload: Any) -> None:
    filename = os.path.basename(str(path or ""))
    if filename not in {"job.json", "report_meta.json"}:
        return
    caller_frame = None
    for frame_info in inspect.stack()[2:]:
        if os.path.abspath(frame_info.filename) != os.path.abspath(__file__):
            caller_frame = frame_info
            break
    caller_file = os.path.relpath(caller_frame.filename, os.getcwd()) if caller_frame else "<unknown>"
    caller_function = caller_frame.function if caller_frame else "<unknown>"
    report_version = ""
    if isinstance(payload, dict):
        report_version = str(payload.get("report_version") or "").strip()
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(
        "[json_writer_trace] "
        f"file={caller_file} "
        f"function={caller_function} "
        f"source={_json_writer_source(payload)} "
        f"timestamp={timestamp} "
        f"report_version={report_version or '<empty>'} "
        f"target={path}"
    )

def write_json(path: str, payload: Any) -> None:
    ensure_dir(os.path.dirname(path))
    _trace_json_writer(path, payload)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
